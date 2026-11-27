from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.clock import freeze_now
from app.models import Notification, QCell, Question, Recommendation, Response, StudySession, TopicMastery
from app.services import notify
from tests.conftest import FROZEN_NOW, make_client, register

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


def first_topic(client, subject_name_prefix: str = "Mathematics") -> dict:
    subjects = client.get("/api/subjects").json()
    subject = next(s for s in subjects if s["name"].startswith(subject_name_prefix))
    client.post(f"/api/subjects/{subject['id']}/enroll")
    return {"subject": subject, "topic": client.get(f"/api/subjects/{subject['id']}").json()["topics"][0]}


def answer_payload(db, questions: list[dict], correct: bool = True) -> list[dict]:
    answers = []
    for item in questions:
        key = db.get(Question, item["id"]).correct_index
        choice = key if correct else (key + 1) % len(item["choices"])
        answers.append({"question_id": item["id"], "chosen_index": choice})
    return answers


def finish_diagnostic(client, db, topic_id: int, correct: bool = True) -> dict:
    questions = client.get(f"/api/topics/{topic_id}/questions", params={"mode": "diagnostic"}).json()
    response = client.post(
        "/api/assessments/submit",
        json={"topic_id": topic_id, "context": "diagnostic", "answers": answer_payload(db, questions, correct)},
    )
    assert response.status_code == 200, response.text
    return response.json()


# ---------- auth ----------

def test_register_login_logout_cycle(client):
    user = register(client)
    assert user["email"] == "ana@example.com"
    assert client.get("/api/auth/me").json()["name"] == "Ana Reyes"
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/login", json={"email": "ANA@example.com", "password": "correct-horse-1"}).status_code == 200


def test_duplicate_email_and_weak_password_rejected(client):
    register(client)
    duplicate = client.post("/api/auth/register", json={"email": "ana@example.com", "name": "X", "password": "correct-horse-1"})
    assert duplicate.status_code == 409 and duplicate.json()["detail"]["code"] == "email_taken"
    weak = client.post("/api/auth/register", json={"email": "b@example.com", "name": "B", "password": "short"})
    assert weak.status_code == 422


def test_wrong_password_and_rate_limit(client):
    register(client)
    for _ in range(8):
        assert client.post("/api/auth/login", json={"email": "ana@example.com", "password": "wrong-password"}).status_code == 401
    blocked = client.post("/api/auth/login", json={"email": "ana@example.com", "password": "correct-horse-1"})
    assert blocked.status_code == 429


def test_protected_routes_require_login(client):
    for path in ("/api/subjects", "/api/commitments", "/api/notifications", "/api/progress"):
        assert client.get(path).status_code == 401


def test_settings_validation(client, student):
    ok = client.patch("/api/auth/me", json={"study_window_start": 420, "study_window_end": 1260, "buffer_minutes": 10})
    assert ok.status_code == 200 and ok.json()["study_window_start"] == 420
    bad = client.patch("/api/auth/me", json={"study_window_start": 600, "study_window_end": 630})
    assert bad.status_code == 422


# ---------- built-in content, diagnostic, BKT ----------

def test_builtin_subjects_visible_and_diagnostic_updates_mastery(client, student, samples, db):
    chosen = first_topic(client)
    topic = chosen["topic"]
    assert topic["ready"] and not topic["diagnostic_done"]
    result = finish_diagnostic(client, db, topic["id"], correct=True)
    assert result["correct_count"] == result["total"] == 3
    assert result["mastery_after"] > result["mastery_before"]
    row = db.scalar(select(TopicMastery).where(TopicMastery.topic_id == topic["id"]))
    assert row.diagnostic_done and row.response_count == 3
    assert db.scalar(select(Response.id).where(Response.topic_id == topic["id"])) is not None

    again = client.get(f"/api/topics/{topic['id']}/questions", params={"mode": "diagnostic"})
    assert again.status_code == 409


def test_wrong_answers_lower_mastery(client, student, samples, db):
    topic = first_topic(client)["topic"]
    result = finish_diagnostic(client, db, topic["id"], correct=False)
    assert result["mastery_after"] < result["mastery_before"]


def test_cannot_assess_without_enrollment(client, student, samples):
    subjects = client.get("/api/subjects").json()
    topic = client.get(f"/api/subjects/{subjects[0]['id']}").json()["topics"][0]
    assert client.get(f"/api/topics/{topic['id']}/questions", params={"mode": "diagnostic"}).status_code == 409


def test_invalid_answer_submissions_rejected(client, student, samples, db):
    topic = first_topic(client)["topic"]
    questions = client.get(f"/api/topics/{topic['id']}/questions", params={"mode": "diagnostic"}).json()
    qid = questions[0]["id"]
    duplicate = client.post("/api/assessments/submit", json={"topic_id": topic["id"], "context": "diagnostic",
                            "answers": [{"question_id": qid, "chosen_index": 0}, {"question_id": qid, "chosen_index": 1}]})
    assert duplicate.status_code == 400
    foreign = client.post("/api/assessments/submit", json={"topic_id": topic["id"], "context": "diagnostic",
                          "answers": [{"question_id": 99999, "chosen_index": 0}]})
    assert foreign.status_code == 400
    out_of_range = client.post("/api/assessments/submit", json={"topic_id": topic["id"], "context": "diagnostic",
                              "answers": [{"question_id": qid, "chosen_index": 5}]})
    assert out_of_range.status_code == 400
    empty = client.post("/api/assessments/submit", json={"topic_id": topic["id"], "context": "diagnostic", "answers": []})
    assert empty.status_code == 422
    assert db.scalar(select(Response.id)) is None


def test_questions_never_expose_answer_key(client, student, samples):
    topic = first_topic(client)["topic"]
    for item in client.get(f"/api/topics/{topic['id']}/questions", params={"mode": "diagnostic"}).json():
        assert set(item) == {"id", "text", "choices"}


# ---------- personal content and isolation ----------

BULK = """What is 2 + 2?
A) 3
B) 4
C) 5
Answer: B
Explanation: Basic addition.

Capital of France?
A. Paris
B. Rome
C. Madrid
Answer: A

Bad question with no key
A) one
B) two
"""


def make_personal_topic(client) -> tuple[int, int]:
    subject = client.post("/api/subjects", json={"name": "My Elective"}).json()
    topic = client.post(f"/api/subjects/{subject['id']}/topics", json={"name": "Chapter 1"}).json()
    return subject["id"], topic["id"]


def test_bulk_question_entry_reports_errors_and_dedupes(client, student):
    _, topic_id = make_personal_topic(client)
    result = client.post(f"/api/topics/{topic_id}/questions/bulk", json={"text": BULK}).json()
    assert result["created"] == 2
    assert len(result["errors"]) == 1 and "Question 3" in result["errors"][0]
    again = client.post(f"/api/topics/{topic_id}/questions/bulk", json={"text": BULK}).json()
    assert again["created"] == 0
    assert len(client.get(f"/api/topics/{topic_id}/my-questions").json()) == 2


def test_topic_needs_minimum_questions_before_assessment(client, student):
    _, topic_id = make_personal_topic(client)
    client.post(f"/api/topics/{topic_id}/questions/bulk", json={"text": BULK})
    topic = client.get(f"/api/topics/{topic_id}").json()
    assert not topic["ready"] and topic["question_count"] == 2
    blocked = client.get(f"/api/topics/{topic_id}/questions", params={"mode": "diagnostic"})
    assert blocked.status_code == 409 and blocked.json()["detail"]["code"] == "not_enough_questions"


def test_csv_question_import(client, student):
    _, topic_id = make_personal_topic(client)
    csv_text = "question,choice_a,choice_b,choice_c,correct,explanation\nWhat is 1+1?,1,2,3,B,Add\nBad,x,y,z,Q,\n"
    response = client.post(f"/api/topics/{topic_id}/questions/csv", files={"file": ("q.csv", csv_text.encode(), "text/csv")})
    assert response.status_code == 201
    assert response.json()["created"] == 1 and len(response.json()["errors"]) == 1
    missing = client.post(f"/api/topics/{topic_id}/questions/csv", files={"file": ("q.csv", b"foo,bar\n1,2\n", "text/csv")})
    assert missing.status_code == 422


def test_personal_content_is_private_to_owner(client, student):
    subject_id, topic_id = make_personal_topic(client)
    client.post(f"/api/topics/{topic_id}/questions/bulk", json={"text": BULK})
    other = make_client("bo@example.com")
    assert all(s["id"] != subject_id for s in other.get("/api/subjects").json())
    assert other.get(f"/api/subjects/{subject_id}").status_code == 404
    assert other.get(f"/api/topics/{topic_id}").status_code == 404
    assert other.get(f"/api/topics/{topic_id}/my-questions").status_code == 404
    assert other.post(f"/api/topics/{topic_id}/questions/bulk", json={"text": BULK}).status_code == 404
    assert other.delete(f"/api/subjects/{subject_id}").status_code == 404


def test_cannot_modify_builtin_subject_or_topics(client, student, samples):
    subject = client.get("/api/subjects").json()[0]
    assert subject["is_builtin"]
    assert client.post(f"/api/subjects/{subject['id']}/topics", json={"name": "Hack"}).status_code == 404
    assert client.delete(f"/api/subjects/{subject['id']}").status_code == 404
    topic = client.get(f"/api/subjects/{subject['id']}").json()["topics"][0]
    assert client.delete(f"/api/topics/{topic['id']}").status_code == 404


def test_student_questions_are_private_even_on_builtin_topic(client, student, samples, db):
    topic = first_topic(client)["topic"]
    before = client.get(f"/api/topics/{topic['id']}").json()["question_count"]
    client.post(f"/api/topics/{topic['id']}/questions", json={"text": "Mine only?", "choices": ["yes", "no"], "correct_index": 0})
    assert client.get(f"/api/topics/{topic['id']}").json()["question_count"] == before + 1
    other = make_client("cy@example.com")
    assert other.get(f"/api/topics/{topic['id']}").json()["question_count"] == before


def test_question_validation(client, student):
    _, topic_id = make_personal_topic(client)
    bad_key = client.post(f"/api/topics/{topic_id}/questions", json={"text": "Q?", "choices": ["a", "b"], "correct_index": 2})
    same_choices = client.post(f"/api/topics/{topic_id}/questions", json={"text": "Q?", "choices": ["a", "A"], "correct_index": 0})
    assert bad_key.status_code == 422 and same_choices.status_code == 422


# ---------- materials ----------

def test_material_upload_download_and_privacy(client, student):
    subject_id, topic_id = make_personal_topic(client)
    upload = client.post("/api/materials/upload", data={"subject_id": subject_id, "topic_id": topic_id},
                         files={"file": ("../../notes.pdf", PDF_BYTES, "application/pdf")})
    assert upload.status_code == 201, upload.text
    material = upload.json()
    assert material["original_name"] == "notes.pdf"
    download = client.get(f"/api/materials/{material['id']}/file")
    assert download.status_code == 200 and download.content == PDF_BYTES
    assert download.headers["x-content-type-options"] == "nosniff"
    other = make_client("di@example.com")
    assert other.get(f"/api/materials/{material['id']}/file").status_code == 404
    assert other.delete(f"/api/materials/{material['id']}").status_code == 404
    assert client.delete(f"/api/materials/{material['id']}").status_code == 204
    assert client.get(f"/api/materials/{material['id']}/file").status_code == 404


@pytest.mark.parametrize(
    ("name", "content", "code"),
    [
        ("virus.exe", b"MZ....", "unsupported_file"),
        ("fake.pdf", b"not really a pdf", "file_mismatch"),
        ("empty.txt", b"", "empty_file"),
        ("bin.txt", b"abc\x00def", "file_mismatch"),
    ],
)
def test_material_upload_rejections(client, student, name, content, code):
    subject_id, _ = make_personal_topic(client)
    response = client.post("/api/materials/upload", data={"subject_id": subject_id}, files={"file": (name, content, "application/octet-stream")})
    assert response.status_code == 400 and response.json()["detail"]["code"] == code


def test_material_size_limit(client, student, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "max_upload_bytes", 1024)
    subject_id, _ = make_personal_topic(client)
    response = client.post("/api/materials/upload", data={"subject_id": subject_id},
                           files={"file": ("big.txt", b"a" * 5000, "text/plain")})
    assert response.status_code == 413


def test_notes_links_and_topic_mismatch(client, student, samples):
    subject_id, topic_id = make_personal_topic(client)
    assert client.post("/api/materials/note", json={"subject_id": subject_id, "topic_id": topic_id, "title": "Summary", "kind": "note", "body": "Key ideas"}).status_code == 201
    assert client.post("/api/materials/note", json={"subject_id": subject_id, "title": "Bad", "kind": "link", "body": "javascript:alert(1)"}).status_code == 422
    builtin = client.get("/api/subjects").json()[0]
    builtin_topic = client.get(f"/api/subjects/{builtin['id']}").json()["topics"][0]
    mismatch = client.post("/api/materials/note", json={"subject_id": subject_id, "topic_id": builtin_topic["id"], "title": "x", "kind": "note", "body": "y"})
    assert mismatch.status_code == 400
    assert len(client.get(f"/api/subjects/{subject_id}/materials").json()) == 1


# ---------- schedule ----------

def commitment(title="Algebra class", kind="class", start="2026-03-02T09:00:00", end="2026-03-02T10:30:00", **extra) -> dict:
    return {"title": title, "kind": kind, "start_at": start, "end_at": end, **extra}


def test_commitment_crud_and_validation(client, student):
    created = client.post("/api/commitments", json=commitment(repeat_weekly=True))
    assert created.status_code == 201
    cid = created.json()["id"]
    assert client.put(f"/api/commitments/{cid}", json=commitment(title="Renamed")).json()["title"] == "Renamed"
    assert len(client.get("/api/commitments").json()) == 1
    assert client.post("/api/commitments", json=commitment(end="2026-03-02T08:00:00")).status_code == 422
    assert client.post("/api/commitments", json=commitment(kind="nap")).status_code == 422
    assert client.post("/api/commitments", json=commitment(end="2026-03-04T10:00:00")).status_code == 422
    assert client.post("/api/commitments", json=commitment(start="2026-03-02T09:00:00+08:00")).status_code == 422
    assert client.delete(f"/api/commitments/{cid}").status_code == 204
    assert client.get("/api/commitments").json() == []


def test_commitments_are_private(client, student):
    cid = client.post("/api/commitments", json=commitment()).json()["id"]
    other = make_client("ed@example.com")
    assert other.put(f"/api/commitments/{cid}", json=commitment()).status_code == 404
    assert other.delete(f"/api/commitments/{cid}").status_code == 404
    assert other.get("/api/commitments").json() == []


def test_schedule_expands_weekly_commitments(client, student):
    client.post("/api/commitments", json=commitment(title="Training", kind="training", start="2026-03-03T16:00:00", end="2026-03-03T18:00:00", repeat_weekly=True))
    week = client.get("/api/schedule", params={"start": "2026-03-09T00:00:00", "end": "2026-03-16T00:00:00"}).json()
    assert [c["start_at"] for c in week["commitments"]] == ["2026-03-10T16:00:00"]
    assert client.get("/api/schedule", params={"start": "2026-03-09T00:00:00", "end": "2026-01-01T00:00:00"}).status_code == 400


def test_requirements_validate_links(client, student, samples):
    chosen = first_topic(client)
    ok = client.post("/api/requirements", json={"title": "Quiz 1", "due_at": "2026-03-04T10:00:00", "topic_id": chosen["topic"]["id"]})
    assert ok.status_code == 201 and ok.json()["subject_id"] == chosen["subject"]["id"]
    assert client.post("/api/requirements", json={"title": "x", "due_at": "2026-03-04T10:00:00", "subject_id": 9999}).status_code == 404
    assert client.patch(f"/api/requirements/{ok.json()['id']}", json={"done": True}).json()["done"] is True


# ---------- recommendation, scheduling, RL loop ----------

def ready_student(client, db) -> int:
    chosen = first_topic(client)
    topics = client.get(f"/api/subjects/{chosen['subject']['id']}").json()["topics"]
    for topic in topics:
        finish_diagnostic(client, db, topic["id"], correct=False)
    return topics[0]["id"]


def test_recommendation_requires_diagnostic_first(client, student, samples):
    first_topic(client)
    response = client.post("/api/recommendations/next")
    assert response.status_code == 409 and response.json()["detail"]["code"] == "diagnostic_needed"


def test_recommendation_requires_enrollment(client, student, samples):
    response = client.post("/api/recommendations/next")
    assert response.status_code == 409 and response.json()["detail"]["code"] == "no_topics"


def test_full_learning_loop_updates_q_table_and_logs(client, student, samples, db):
    topic_id = ready_student(client, db)
    recommendation = client.post("/api/recommendations/next").json()
    assert recommendation["topic_id"] == topic_id
    assert recommendation["session_status"] == "scheduled"
    assert datetime.fromisoformat(recommendation["start_at"]) >= FROZEN_NOW
    assert client.post("/api/recommendations/next").json()["id"] == recommendation["id"]

    started = client.post(f"/api/recommendations/{recommendation['id']}/start").json()
    if started["questions"]:
        submit = client.post(f"/api/recommendations/{recommendation['id']}/submit",
                             json={"answers": answer_payload(db, started["questions"], True)})
        assert submit.status_code == 200 and submit.json()["mastery_after"] > submit.json()["mastery_before"]
    else:
        assert client.post(f"/api/recommendations/{recommendation['id']}/complete").status_code == 200

    stored = db.get(Recommendation, recommendation["id"])
    db.refresh(stored)
    assert stored.status == "completed" and stored.reward is not None
    assert stored.state_key and stored.next_state_key and stored.q_value_after is not None
    cell = db.get(QCell, (stored.state_key, stored.activity_type))
    assert cell is not None and cell.visits == 1
    assert db.scalar(select(StudySession.status).where(StudySession.recommendation_id == stored.id)) == "completed"
    assert client.post(f"/api/recommendations/{recommendation['id']}/submit", json={"answers": [{"question_id": 1, "chosen_index": 0}]}).status_code == 409
    assert client.post("/api/recommendations/next").json()["id"] != recommendation["id"]


def test_skip_gives_negative_reward(client, student, samples, db):
    ready_student(client, db)
    recommendation = client.post("/api/recommendations/next").json()
    skipped = client.post(f"/api/recommendations/{recommendation['id']}/skip").json()
    assert skipped["reward"] == -0.2 and skipped["recommendation"]["status"] == "skipped"


def test_recommendation_fits_around_commitments(client, student, samples, db):
    client.post("/api/commitments", json=commitment(title="Class", start="2026-03-02T08:00:00", end="2026-03-02T12:00:00"))
    ready_student(client, db)
    recommendation = client.post("/api/recommendations/next").json()
    start = datetime.fromisoformat(recommendation["start_at"])
    end = datetime.fromisoformat(recommendation["end_at"])
    assert start >= datetime(2026, 3, 2, 12, 15)
    assert (end - start) == timedelta(minutes=recommendation["duration_minutes"])


def test_no_free_time_reports_clearly_and_notifies(client, student, samples, db):
    ready_student(client, db)
    for day in range(8):
        base = datetime(2026, 3, 2) + timedelta(days=day)
        client.post("/api/commitments", json=commitment(title="All day", start=base.replace(hour=0).isoformat(), end=(base + timedelta(hours=23, minutes=59)).isoformat()))
    response = client.post("/api/recommendations/next")
    assert response.status_code == 409 and response.json()["detail"]["code"] == "no_free_time"
    assert any(n["kind"] == "schedule_change" for n in client.get("/api/notifications").json())


def test_new_commitment_moves_conflicting_session_and_notifies(client, student, samples, db):
    ready_student(client, db)
    recommendation = client.post("/api/recommendations/next").json()
    start = datetime.fromisoformat(recommendation["start_at"])
    client.post("/api/commitments", json=commitment(title="Surprise training", kind="training", start=(start - timedelta(minutes=10)).isoformat(), end=(start + timedelta(minutes=40)).isoformat()))
    session = db.scalar(select(StudySession).where(StudySession.recommendation_id == recommendation["id"]))
    db.refresh(session)
    assert session.status == "scheduled" and session.start_at > start
    assert session.start_at >= start + timedelta(minutes=40)
    assert any(n["title"] == "Study session moved" for n in client.get("/api/notifications").json())


def test_session_flagged_when_no_alternative_slot(client, student, samples, db):
    ready_student(client, db)
    recommendation = client.post("/api/recommendations/next").json()
    for day in range(8):
        base = datetime(2026, 3, 2) + timedelta(days=day)
        client.post("/api/commitments", json=commitment(title="Blocked", start=base.replace(hour=0).isoformat(), end=(base + timedelta(hours=23, minutes=59)).isoformat()))
    session = db.scalar(select(StudySession).where(StudySession.recommendation_id == recommendation["id"]))
    db.refresh(session)
    assert session.status == "needs_reschedule" and session.start_at is None
    assert client.post("/api/schedule/replan").json() == {"placed": 0}


def test_urgent_deadline_changes_topic_priority(client, student, samples, db):
    subject = first_topic(client)["subject"]
    topics = client.get(f"/api/subjects/{subject['id']}").json()["topics"]
    for topic in topics[:2]:
        finish_diagnostic(client, db, topic["id"], correct=True if topic is topics[0] else False)
    client.post("/api/requirements", json={"title": "Exam", "due_at": (FROZEN_NOW + timedelta(days=1)).isoformat(), "topic_id": topics[0]["id"]})
    first = client.post("/api/recommendations/next").json()
    assert first["topic_id"] in {topics[0]["id"], topics[1]["id"]}
    assert "deadline" in first["reason"] or first["topic_id"] == topics[1]["id"]


def test_recommendations_are_private(client, student, samples, db):
    ready_student(client, db)
    recommendation = client.post("/api/recommendations/next").json()
    other = make_client("fi@example.com")
    assert other.get(f"/api/recommendations/{recommendation['id']}").status_code == 404
    assert other.post(f"/api/recommendations/{recommendation['id']}/skip").status_code == 404


# ---------- notifications ----------

def test_reminders_are_generated_once_and_become_visible_at_fire_time(client, student, samples, db):
    ready_student(client, db)
    recommendation = client.post("/api/recommendations/next").json()
    start = datetime.fromisoformat(recommendation["start_at"])
    client.patch("/api/auth/me", json={"reminder_minutes": 15})
    freeze_now(start - timedelta(hours=2))
    assert notify.generate_due_reminders(db) == 1
    assert notify.generate_due_reminders(db) == 0
    reminders = db.scalars(select(Notification).where(Notification.kind == "session_reminder")).all()
    assert len(reminders) == 1 and reminders[0].scheduled_for == start - timedelta(minutes=15)
    assert not any(n["kind"] == "session_reminder" for n in client.get("/api/notifications").json())
    freeze_now(start - timedelta(minutes=10))
    visible = [n for n in client.get("/api/notifications").json() if n["kind"] == "session_reminder"]
    assert len(visible) == 1


def test_deadline_notification_and_read_state(client, student, db):
    client.post("/api/requirements", json={"title": "Essay", "due_at": (FROZEN_NOW + timedelta(hours=5)).isoformat()})
    assert notify.generate_due_reminders(db) == 1
    assert notify.generate_due_reminders(db) == 0
    count = client.get("/api/notifications/unread-count").json()["count"]
    assert count == 1
    nid = client.get("/api/notifications").json()[0]["id"]
    assert client.post(f"/api/notifications/{nid}/read").status_code == 204
    assert client.get("/api/notifications/unread-count").json()["count"] == 0
    other = make_client("gi@example.com")
    assert other.post(f"/api/notifications/{nid}/read").status_code == 404


def test_notifications_go_to_the_right_user_only(client, student, db):
    client.post("/api/requirements", json={"title": "Essay", "due_at": (FROZEN_NOW + timedelta(hours=5)).isoformat()})
    notify.generate_due_reminders(db)
    other = make_client("hu@example.com")
    assert other.get("/api/notifications").json() == []


def test_push_not_configured_degrades_gracefully(client, student, db):
    assert client.get("/api/push/public-key").status_code == 503
    sub = {"endpoint": "https://push.example.com/abc123456", "keys": {"p256dh": "k", "auth": "a"}}
    assert client.post("/api/push/subscribe", json=sub).status_code == 204
    assert client.post("/api/push/subscribe", json={**sub, "endpoint": "http://insecure.example.com/xyz1234"}).status_code == 422
    client.post("/api/requirements", json={"title": "Essay", "due_at": (FROZEN_NOW + timedelta(hours=5)).isoformat()})
    notify.generate_due_reminders(db)
    assert notify.dispatch_push(db) == 0
    assert db.scalar(select(Notification.pushed_at)) is not None
    assert client.post("/api/push/unsubscribe", json={"endpoint": sub["endpoint"]}).status_code == 204


# ---------- progress ----------

def test_progress_lists_assessed_topics_and_history(client, student, samples, db):
    topic = first_topic(client)["topic"]
    assert client.get("/api/progress").json() == []
    finish_diagnostic(client, db, topic["id"], correct=True)
    progress = client.get("/api/progress").json()
    assert len(progress) == 1 and progress[0]["responses"] == 3 and progress[0]["correct"] == 3
    history = client.get(f"/api/progress/topics/{topic['id']}").json()
    assert [p["mastery"] for p in history["points"]] == sorted(p["mastery"] for p in history["points"])


def test_unknown_topic_returns_not_found(client, student):
    assert client.get("/api/topics/424242").status_code == 404
    assert client.get("/api/subjects/424242").status_code == 404
