"""Entry point for turning an uploaded file into a Document, with the parser isolated in a limited child process."""

import logging
import multiprocessing
import resource
from pathlib import Path

from app.ingest.document import Document, IngestError
from app.ingest.limits import (
    MAX_TEXT_CHARS,
    PARSE_CPU_SECONDS,
    PARSE_MEMORY_BYTES,
    PARSE_TIMEOUT_SECONDS,
)
from app.ingest.office import parse_docx, parse_pptx
from app.ingest.pdf import parse_pdf
from app.ingest.plain import decode_text, parse_text

logger = logging.getLogger(__name__)

FORMATS = {".pdf": "pdf", ".docx": "docx", ".pptx": "pptx", ".txt": "txt", ".md": "txt"}


def format_for(filename: str) -> str | None:
    return FORMATS.get(Path(filename).suffix.lower())


def parse_file(path: Path, format: str) -> Document:
    if format == "pdf":
        return parse_pdf(path)
    if format == "docx":
        return parse_docx(path)
    if format == "pptx":
        return parse_pptx(path)
    if format == "txt":
        return parse_text(decode_text(path.read_bytes()), "txt")
    raise IngestError("unsupported_file", "This file type cannot be read for questions.")


def _apply_limits() -> None:
    for limit, value in ((resource.RLIMIT_CPU, PARSE_CPU_SECONDS), (resource.RLIMIT_AS, PARSE_MEMORY_BYTES)):
        try:
            resource.setrlimit(limit, (value, value))
        except (ValueError, OSError):
            pass  # macOS does not enforce RLIMIT_AS; the wall-clock timeout still applies.


def _child(connection, path: str, format: str) -> None:  # noqa: ANN001
    _apply_limits()
    try:
        connection.send(("ok", parse_file(Path(path), format).to_dict()))
    except IngestError as error:
        connection.send(("error", (error.code, error.message)))
    except MemoryError:
        connection.send(("error", ("too_large", "This document needs more memory than allowed.")))
    except Exception:  # noqa: BLE001  (any parser failure is reported as unreadable, never raised into the app)
        connection.send(("error", ("unreadable", "This document could not be read.")))
    finally:
        connection.close()


def run_isolated(target, args: tuple, timeout: float) -> tuple[str, object]:  # noqa: ANN001
    """Run `target(connection, *args)` in a spawned process and return what it sends, or raise on timeout/crash."""
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=target, args=(sender, *args), daemon=True)
    process.start()
    sender.close()
    try:
        if not receiver.poll(timeout):
            raise IngestError("timeout", "Reading this document took too long.")
        return receiver.recv()
    except EOFError as error:
        raise IngestError("too_large", "This document needs more resources than allowed.") from error
    finally:
        receiver.close()
        process.join(1)
        if process.is_alive():
            process.kill()
            process.join(1)


def truncate(document: Document, limit: int = MAX_TEXT_CHARS) -> Document:
    total = 0
    for index, block in enumerate(document.blocks):
        total += len(block.text)
        if total > limit:
            document.blocks = document.blocks[:index]
            document.warnings.append("truncated")
            break
    return document


def extract_document(path: Path, format: str, timeout: float = PARSE_TIMEOUT_SECONDS) -> Document:
    status, payload = run_isolated(_child, (str(path), format), timeout)
    if status == "error":
        code, message = payload
        logger.info("Extraction rejected a %s file: %s", format, code)
        raise IngestError(code, message)
    return truncate(Document.from_dict(payload))
