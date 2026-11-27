import os
import tempfile
from datetime import datetime

_upload_dir = tempfile.mkdtemp(prefix="sideline-test-uploads-")
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:")
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["AUTO_MIGRATE"] = "false"
os.environ["UPLOAD_DIR"] = _upload_dir
os.environ["SECRET_KEY"] = "test-secret-key-test-secret-key-test"
os.environ["VAPID_PUBLIC_KEY"] = ""
os.environ["VAPID_PRIVATE_KEY"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api import auth as auth_module  # noqa: E402
from app.core import ratelimit  # noqa: E402
from app.core.clock import freeze_now  # noqa: E402
from app.core.db import Base, SessionLocal, engine  # noqa: E402
from app.main import create_app  # noqa: E402
from app.services.seed import seed_samples  # noqa: E402

FROZEN_NOW = datetime(2026, 3, 2, 8, 0, 0)  # a Monday, 08:00


@pytest.fixture(autouse=True)
def fresh_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    auth_module.reset_rate_limits()
    ratelimit.reset_all()
    freeze_now(FROZEN_NOW)
    yield
    freeze_now(None)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def samples(db):
    seed_samples(db)


def register(client: TestClient, email: str = "ana@example.com", name: str = "Ana Reyes") -> dict:
    response = client.post("/api/auth/register", json={"email": email, "name": name, "password": "correct-horse-1"})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def student(client):
    return register(client)


def make_client(email: str) -> TestClient:
    other = TestClient(create_app())
    register(other, email=email, name="Other Student")
    return other
