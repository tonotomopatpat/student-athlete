from typing import Annotated

from fastapi import APIRouter, File, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, select

from app.api.catalog import subject_detail
from app.api.deps import CurrentUser, DbSession
from app.core.errors import bad_request, conflict
from app.core.ratelimit import syllabus_limiter
from app.ingest.document import IngestError
from app.ingest.extract import extract_document, format_for
from app.ingest.syllabus import propose_topics
from app.models import Subject, Topic
from app.schemas import SubjectDetailOut, SyllabusConfirmIn, SyllabusPreviewOut
from app.services import content
from app.services.materials import delete_stored_file, store_upload, stored_path

router = APIRouter(prefix="/syllabus", tags=["syllabus"])


@router.post("/preview", response_model=SyllabusPreviewOut)
async def preview_syllabus(user: CurrentUser, file: Annotated[UploadFile, File()]) -> SyllabusPreviewOut:
    """Read a syllabus and propose a subject and topic list. Nothing is saved; the file is discarded."""
    syllabus_limiter.hit(user.id)
    stored_name, original_name, _ = await store_upload(file)
    try:
        format = format_for(stored_name)
        if format is None:
            raise bad_request("unsupported_file", "Upload the syllabus as PDF, DOCX, PPTX or TXT.")
        document = await run_in_threadpool(extract_document, stored_path(stored_name), format)
    except IngestError as error:
        raise bad_request(error.code, error.message) from error
    finally:
        delete_stored_file(stored_name)
    proposal = propose_topics(document)
    if "no_text_layer" in document.warnings:
        proposal.warnings.append("no_text_layer")
    return SyllabusPreviewOut(
        name=proposal.name or original_name.rsplit(".", 1)[0][:160],
        code=proposal.code,
        topics=proposal.topics,
        warnings=proposal.warnings,
    )


@router.post("/confirm", response_model=SubjectDetailOut, status_code=201)
def confirm_syllabus(payload: SyllabusConfirmIn, user: CurrentUser, db: DbSession) -> SubjectDetailOut:
    duplicate = db.scalar(
        select(Subject.id).where(Subject.owner_id == user.id, func.lower(Subject.name) == payload.name.lower())
    )
    if duplicate:
        raise conflict("subject_exists", "You already have a subject with this name.")
    subject = Subject(name=payload.name, description=payload.description, owner_id=user.id)
    db.add(subject)
    db.flush()
    for position, name in enumerate(payload.topics, start=1):
        db.add(Topic(subject_id=subject.id, name=name, position=position))
    content.enroll(db, user, subject.id)
    db.commit()
    return subject_detail(db, user, subject)
