"""Programmatic Alembic helpers used by the CLI, app startup and tests."""

import logging

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.core.config import BACKEND_DIR, get_settings

logger = logging.getLogger(__name__)

BASELINE_REVISION = "0001_baseline"


def alembic_config(database_url: str | None = None) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.attributes["database_url"] = database_url or get_settings().database_url
    return config


def upgrade_to_head(database_url: str | None = None) -> None:
    """Bring the database to the latest schema.

    Databases created before migrations existed (tables present, no version table) are stamped at the
    baseline first, because the baseline describes exactly that schema.
    """
    url = database_url or get_settings().database_url
    engine = create_engine(url)
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    config = alembic_config(url)
    if "users" in tables and "alembic_version" not in tables:
        logger.info("Stamping pre-migration database at %s", BASELINE_REVISION)
        command.stamp(config, BASELINE_REVISION)
    command.upgrade(config, "head")


def downgrade_to(revision: str, database_url: str | None = None) -> None:
    command.downgrade(alembic_config(database_url), revision)
