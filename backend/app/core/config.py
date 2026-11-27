from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    database_url: str = f"sqlite:///{BACKEND_DIR / 'data' / 'sideline.db'}"
    secret_key: str = "dev-only-secret-change-me-dev-only-secret"
    timezone: str = "Asia/Manila"
    cookie_secure: bool = False
    token_minutes: int = 60 * 12
    upload_dir: Path = BACKEND_DIR / "data" / "uploads"
    max_upload_bytes: int = 15 * 1024 * 1024
    scheduler_enabled: bool = True
    auto_migrate: bool = True
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:admin@example.com"
    frontend_dist: Path = BACKEND_DIR.parent / "frontend" / "dist"


@lru_cache
def get_settings() -> Settings:
    return Settings()
