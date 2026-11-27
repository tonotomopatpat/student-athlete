import os

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from app.core.db import Base
from app.core.migrations import downgrade_to, upgrade_to_head

pytestmark = pytest.mark.skipif(
    "TEST_DATABASE_URL" in os.environ, reason="migration round-trip uses its own SQLite file"
)


def _schema_diff(url: str) -> list:
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            return compare_metadata(MigrationContext.configure(connection), Base.metadata)
    finally:
        engine.dispose()


def _tables(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_migrations_match_models_and_round_trip(tmp_path):
    url = f"sqlite:///{tmp_path / 'migrate.db'}"
    upgrade_to_head(url)
    assert _schema_diff(url) == []
    downgrade_to("base", url)
    assert _tables(url) <= {"alembic_version"}
    upgrade_to_head(url)
    assert _schema_diff(url) == []


def test_legacy_database_without_version_table_is_stamped(tmp_path):
    url = f"sqlite:///{tmp_path / 'legacy.db'}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    engine.dispose()
    upgrade_to_head(url)
    assert "alembic_version" in _tables(url)
    assert _schema_diff(url) == []
