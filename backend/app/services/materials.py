import logging
import os
import re
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError, bad_request
from app.models import Material

logger = logging.getLogger(__name__)

CHUNK_SIZE = 64 * 1024

ALLOWED_TYPES: dict[str, tuple[str, bool]] = {
    ".pdf": ("application/pdf", True),
    ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", False),
    ".pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", False),
    ".txt": ("text/plain; charset=utf-8", True),
    ".md": ("text/plain; charset=utf-8", True),
    ".png": ("image/png", True),
    ".jpg": ("image/jpeg", True),
    ".jpeg": ("image/jpeg", True),
}


def _matches_signature(extension: str, head: bytes) -> bool:
    if extension == ".pdf":
        return head.startswith(b"%PDF")
    if extension in (".docx", ".pptx"):
        return head.startswith(b"PK\x03\x04")
    if extension == ".png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    if extension in (".jpg", ".jpeg"):
        return head.startswith(b"\xff\xd8\xff")
    if extension in (".txt", ".md"):
        if b"\x00" in head:
            return False
        try:
            head.decode("utf-8")
        except UnicodeDecodeError as error:
            return error.reason == "unexpected end of data"
        return True
    return False


def clean_filename(name: str | None) -> str:
    base = os.path.basename((name or "").replace("\\", "/"))
    base = re.sub(r"[^\w.\- ()]", "_", base).strip()
    return base[:200] or "upload"


def upload_directory() -> Path:
    directory = get_settings().upload_dir
    directory.mkdir(parents=True, exist_ok=True)
    return directory


async def store_upload(file: UploadFile) -> tuple[str, str, str]:
    """Validate and persist an upload. Returns (stored_name, original_name, mime_type)."""
    settings = get_settings()
    original = clean_filename(file.filename)
    extension = Path(original).suffix.lower()
    if extension not in ALLOWED_TYPES:
        raise bad_request("unsupported_file", "Allowed files: PDF, DOCX, PPTX, TXT, MD, PNG, JPG.")
    stored_name = f"{uuid.uuid4().hex}{extension}"
    destination = upload_directory() / stored_name
    size = 0
    head = b""
    try:
        with destination.open("wb") as out:
            while chunk := await file.read(CHUNK_SIZE):
                if not head:
                    head = chunk[:8192]
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise ApiError(413, "file_too_large", f"Files must be {settings.max_upload_bytes // (1024 * 1024)} MB or smaller.")
                out.write(chunk)
        if size == 0:
            raise bad_request("empty_file", "The uploaded file is empty.")
        if not _matches_signature(extension, head):
            raise bad_request("file_mismatch", "The file content does not match its extension.")
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return stored_name, original, ALLOWED_TYPES[extension][0]


def stored_path(stored_name: str) -> Path:
    path = (upload_directory() / stored_name).resolve()
    if path.parent != upload_directory().resolve():
        raise bad_request("invalid_path", "Invalid file reference.")
    return path


def delete_stored_file(stored_name: str | None) -> None:
    if not stored_name:
        return
    try:
        stored_path(stored_name).unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not delete stored file %s", stored_name)


def delete_stored_files_for_subject(db: Session, subject_id: int) -> None:
    for name in db.scalars(select(Material.stored_name).where(Material.subject_id == subject_id)).all():
        delete_stored_file(name)


def inline_allowed(extension: str) -> bool:
    return ALLOWED_TYPES.get(extension, ("", False))[1]
