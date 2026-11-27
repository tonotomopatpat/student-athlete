import threading

import pytest

from app.core.db import SessionLocal, engine
from app.models import QCell
from app.services.recommender import _update_q

pytestmark = pytest.mark.skipif(
    engine.dialect.name == "sqlite", reason="needs a server database with real row locks"
)

WORKERS = 8


def test_concurrent_q_updates_are_all_counted():
    barrier = threading.Barrier(WORKERS)
    errors: list[BaseException] = []

    def complete_activity() -> None:
        session = SessionLocal()
        try:
            barrier.wait()
            _update_q(session, "m1-u0-t2-r0", "practice", 0.5, "m2-u0-t2-r0", ["practice", "quiz"])
            session.commit()
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=complete_activity) for _ in range(WORKERS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    with SessionLocal() as session:
        assert session.get(QCell, ("m1-u0-t2-r0", "practice")).visits == WORKERS
