"""Maintenance commands: python -m app.cli <command>."""

import argparse
import base64
import csv
import hashlib
import hmac
import re
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import select

from app.core.config import BACKEND_DIR, get_settings
from app.core.db import SessionLocal
from app.core.migrations import upgrade_to_head
from app.ml.simulator import pretrain, run_and_save
from app.models import QCell, Recommendation, Response
from app.services.seed import import_questions_csv, seed_samples

DEFAULT_SIMULATION_PATH = BACKEND_DIR / "data" / "simulation_results.json"


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def cmd_migrate(_args: argparse.Namespace) -> None:
    upgrade_to_head()
    print("Database schema is up to date.")


def cmd_seed_samples(_args: argparse.Namespace) -> None:
    upgrade_to_head()
    with SessionLocal() as db:
        report = seed_samples(db)
    print(f"Sample content: {report.subjects} subjects, {report.topics} topics, {report.questions} questions added "
          f"({report.skipped_duplicates} already present).")


def cmd_import_questions(args: argparse.Namespace) -> None:
    upgrade_to_head()
    with SessionLocal() as db:
        report = import_questions_csv(db, Path(args.file))
    if report.errors:
        print("Import failed. Nothing was saved:")
        for error in report.errors[:50]:
            print(f"  {error}")
        sys.exit(1)
    print(f"Imported {report.questions} questions ({report.topics} new topics, {report.subjects} new subjects, "
          f"{report.skipped_duplicates} duplicates skipped).")


def cmd_pretrain(args: argparse.Namespace) -> None:
    """Warm-start the shared Q-table by simulating learners. The result reflects ASSUMED dynamics only."""
    upgrade_to_head()
    learner = pretrain(students=args.students)
    with SessionLocal() as db:
        for (state, action), q_value in learner.q.items():
            cell = db.get(QCell, (state, action))
            visits = learner.visits.get((state, action), 0)
            if cell is None:
                db.add(QCell(state=state, action=action, q_value=q_value, visits=visits))
            else:
                cell.q_value, cell.visits = q_value, visits
        db.commit()
    print(f"Pretrained {len(learner.q)} state-action values from {args.students} simulated students.")


def cmd_simulate(args: argparse.Namespace) -> None:
    payload = run_and_save(Path(args.out), students=args.students, pretrain_students=args.pretrain_students)
    print(f"Saved {args.out}")
    for env_name, policies in payload["results"].items():
        print(f"\n[{env_name}] topics gained per study hour (mean +/- 95% CI)")
        for policy, metrics in policies.items():
            gained = metrics["topics_gained_per_study_hour"]
            print(f"  {policy:20s} {gained['mean']:.3f} +/- {gained['ci95']:.3f}")


def _pseudonym(user_id: int) -> str:
    key = get_settings().secret_key.encode()
    return hmac.new(key, str(user_id).encode(), hashlib.sha256).hexdigest()[:12]


def cmd_export_logs(args: argparse.Namespace) -> None:
    """Export pseudonymized research logs (no emails or names)."""
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with SessionLocal() as db:
        with (out / "recommendations.csv").open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["id", "user", "topic_id", "activity", "state", "q_value", "explored", "epsilon",
                             "available_minutes", "status", "mastery_before", "mastery_after", "reward",
                             "next_state", "q_value_after", "created_at", "completed_at"])
            for r in db.scalars(select(Recommendation).order_by(Recommendation.id)):
                writer.writerow([r.id, _pseudonym(r.user_id), r.topic_id, r.activity_type, r.state_key, r.q_value,
                                 r.explored, r.epsilon, r.available_minutes, r.status, r.mastery_before,
                                 r.mastery_after, r.reward, r.next_state_key, r.q_value_after, r.created_at,
                                 r.completed_at])
        with (out / "responses.csv").open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["user", "topic_id", "question_id", "recommendation_id", "context", "correct",
                             "mastery_before", "mastery_after", "created_at"])
            for r in db.scalars(select(Response).order_by(Response.id)):
                writer.writerow([_pseudonym(r.user_id), r.topic_id, r.question_id, r.recommendation_id, r.context,
                                 r.correct, r.mastery_before, r.mastery_after, r.created_at])
        with (out / "q_table.csv").open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["state", "action", "q_value", "visits"])
            for c in db.scalars(select(QCell).order_by(QCell.state, QCell.action)):
                writer.writerow([c.state, c.action, c.q_value, c.visits])
    print(f"Exported logs to {out}")


def cmd_gen_vapid(args: argparse.Namespace) -> None:
    key = ec.generate_private_key(ec.SECP256R1())
    private = _b64url(key.private_bytes(
        serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ))
    public = _b64url(key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    ))
    if not args.write:
        print(f"VAPID_PUBLIC_KEY={public}\nVAPID_PRIVATE_KEY={private}")
        return
    env_path = BACKEND_DIR / ".env"
    text = env_path.read_text() if env_path.exists() else ""
    for name, value in (("VAPID_PUBLIC_KEY", public), ("VAPID_PRIVATE_KEY", private)):
        line = f"{name}={value}"
        text = re.sub(rf"^{name}=.*$", line, text, flags=re.MULTILINE) if re.search(rf"^{name}=", text, re.MULTILINE) else text + f"\n{line}"
    env_path.write_text(text.lstrip("\n") + ("\n" if not text.endswith("\n") else ""))
    print(f"Wrote VAPID keys to {env_path}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate").set_defaults(func=cmd_migrate)
    sub.add_parser("seed-samples").set_defaults(func=cmd_seed_samples)
    imp = sub.add_parser("import-questions")
    imp.add_argument("file")
    imp.set_defaults(func=cmd_import_questions)
    pre = sub.add_parser("pretrain")
    pre.add_argument("--students", type=int, default=5000)
    pre.set_defaults(func=cmd_pretrain)
    sim = sub.add_parser("simulate")
    sim.add_argument("--students", type=int, default=2000)
    sim.add_argument("--pretrain-students", type=int, default=5000)
    sim.add_argument("--out", default=str(DEFAULT_SIMULATION_PATH))
    sim.set_defaults(func=cmd_simulate)
    exp = sub.add_parser("export-logs")
    exp.add_argument("--out", default=str(BACKEND_DIR / "data" / "exports"))
    exp.set_defaults(func=cmd_export_logs)
    vapid = sub.add_parser("gen-vapid")
    vapid.add_argument("--write", action="store_true", help="write keys into backend/.env")
    vapid.set_defaults(func=cmd_gen_vapid)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
