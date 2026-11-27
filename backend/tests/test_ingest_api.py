from tests.conftest import make_client
from tests.ingest_fixtures import BILLION_LAUGHS, make_docx, rewrite_zip
from tests.test_ingest import LESSON, SYLLABUS


def create_subject(client, topics: list[str]) -> dict:
    response = client.post("/api/syllabus/confirm", json={"name": "Biology", "topics": topics})
    assert response.status_code == 201, response.text
    return response.json()


def upload(client, subject_id: int, name: str, data: bytes, topic_id: int | None = None):
    form = {"subject_id": subject_id} | ({"topic_id": topic_id} if topic_id else {})
    return client.post("/api/materials/upload", data=form, files={"file": (name, data, "application/octet-stream")})


def test_syllabus_preview_then_confirm(client, student):
    preview = client.post("/api/syllabus/preview", files={"file": ("syllabus.txt", SYLLABUS.encode(), "text/plain")})
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["name"] == "Introduction to Psychology" and len(body["topics"]) == 5
    assert client.get("/api/subjects").json() == [s for s in client.get("/api/subjects").json() if s["is_builtin"]]

    confirmed = client.post("/api/syllabus/confirm", json={"name": body["name"], "topics": body["topics"][:3]})
    assert confirmed.status_code == 201
    subject = confirmed.json()
    assert [t["name"] for t in subject["topics"]] == body["topics"][:3]
    assert subject["enrolled"] is True
    again = client.post("/api/syllabus/confirm", json={"name": body["name"].upper(), "topics": ["X"]})
    assert again.status_code == 409


def test_syllabus_confirm_validation(client, student):
    assert client.post("/api/syllabus/confirm", json={"name": "A", "topics": []}).status_code == 422
    assert client.post("/api/syllabus/confirm", json={"name": "A", "topics": ["Cells", "cells"]}).status_code == 422
    assert client.post("/api/syllabus/confirm", json={"name": "A", "topics": ["x" * 161]}).status_code == 422


def test_syllabus_preview_rejects_images_and_hostile_files(client, student):
    png = client.post("/api/syllabus/preview", files={"file": ("s.png", b"\x89PNG\r\n\x1a\n" + b"0" * 20, "image/png")})
    assert png.status_code == 400 and png.json()["detail"]["code"] == "unsupported_file"
    hostile = rewrite_zip(make_docx(lambda doc: doc.add_paragraph("x")), replace={"word/document.xml": BILLION_LAUGHS})
    bad = client.post("/api/syllabus/preview", files={"file": ("s.docx", hostile, "application/octet-stream")})
    assert bad.status_code == 400 and bad.json()["detail"]["code"] == "unsafe_document"


def test_lesson_upload_extracts_and_routes_sections(client, student):
    subject = create_subject(client, ["Cell structure and function", "Photosynthesis and respiration", "Genetics"])
    cells, photo, _ = (t["id"] for t in subject["topics"])
    response = upload(client, subject["id"], "lesson.txt", LESSON.encode())
    assert response.status_code == 201, response.text
    material = response.json()
    assert material["extraction_status"] == "ok" and material["language"] == "en"

    text = client.get(f"/api/materials/{material['id']}/text").json()
    assert "## 1.1 Cell Structure" in text["extracted_text"] and "**cell membrane**" in text["extracted_text"]
    sections = client.get(f"/api/materials/{material['id']}/sections").json()
    assert [(s["title"], s["topic_id"]) for s in sections] == [
        ("CELL BIOLOGY", cells), ("Cell Structure", cells), ("Photosynthesis", photo),
    ]
    assert client.get(f"/api/subjects/{subject['id']}/unsorted").json() == []


def test_unsorted_sections_can_be_assigned_and_survive_rerouting(client, student):
    subject = create_subject(client, ["Genetics"])
    material = upload(client, subject["id"], "notes.txt", b"# Basketball\n\nPassing and dribbling drills for the team.\n").json()
    unsorted = client.get(f"/api/subjects/{subject['id']}/unsorted").json()
    assert [s["title"] for s in unsorted] == ["Basketball"] and unsorted[0]["material_title"] == "notes.txt"

    genetics = subject["topics"][0]["id"]
    section_id = unsorted[0]["id"]
    assigned = client.put(f"/api/materials/{material['id']}/sections/{section_id}", json={"topic_id": genetics})
    assert assigned.status_code == 200 and assigned.json()["assigned_by"] == "student"
    client.post(f"/api/subjects/{subject['id']}/topics", json={"name": "Basketball fundamentals"})
    sections = client.get(f"/api/materials/{material['id']}/sections").json()
    assert sections[0]["topic_id"] == genetics

    foreign = client.put(f"/api/materials/{material['id']}/sections/{section_id}", json={"topic_id": 999999})
    assert foreign.status_code == 400


def test_new_topic_picks_up_unsorted_sections(client, student):
    subject = create_subject(client, ["Genetics"])
    upload(client, subject["id"], "notes.txt", b"# Photosynthesis\n\nPlants convert light into chemical energy.\n")
    assert len(client.get(f"/api/subjects/{subject['id']}/unsorted").json()) == 1
    client.post(f"/api/subjects/{subject['id']}/topics", json={"name": "Photosynthesis"})
    assert client.get(f"/api/subjects/{subject['id']}/unsorted").json() == []


def test_hostile_upload_is_stored_but_marked_failed(client, student):
    subject = create_subject(client, ["Cells"])
    bomb = rewrite_zip(make_docx(lambda doc: doc.add_paragraph("x")), extra={"word/media/pad.bin": b"\0" * (12 * 1024 * 1024)})
    response = upload(client, subject["id"], "bomb.docx", bomb)
    assert response.status_code == 201
    assert response.json()["extraction_status"] == "failed" and response.json()["extraction_error"] == "too_large"
    assert client.get(f"/api/materials/{response.json()['id']}/sections").json() == []


def test_image_upload_waits_for_ocr_and_cannot_be_reextracted(client, student):
    subject = create_subject(client, ["Cells"])
    material = upload(client, subject["id"], "slide.png", b"\x89PNG\r\n\x1a\n" + b"0" * 32).json()
    assert material["extraction_status"] == "pending"
    assert client.post(f"/api/materials/{material['id']}/extract").status_code == 400


def test_notes_are_extracted_and_reextract_works(client, student):
    subject = create_subject(client, ["Cells"])
    note = client.post("/api/materials/note", json={
        "subject_id": subject["id"], "title": "My notes", "kind": "note", "body": "# Cells\n\nThe cell is the unit of life.",
    }).json()
    assert note["extraction_status"] == "ok"
    again = client.post(f"/api/materials/{note['id']}/extract")
    assert again.status_code == 200 and again.json()["extraction_status"] == "ok"


def test_extracted_text_and_sections_are_private(client, student):
    subject = create_subject(client, ["Cells"])
    material = upload(client, subject["id"], "lesson.txt", LESSON.encode()).json()
    other = make_client("mara@example.com")
    for path in (f"/api/materials/{material['id']}/text", f"/api/materials/{material['id']}/sections"):
        assert other.get(path).status_code == 404
    assert other.post(f"/api/materials/{material['id']}/extract").status_code == 404
    assert other.get(f"/api/subjects/{subject['id']}/unsorted").status_code == 404
