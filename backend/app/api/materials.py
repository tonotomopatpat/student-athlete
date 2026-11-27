from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.errors import bad_request, not_found
from app.core.ratelimit import extract_limiter, upload_limiter
from app.models import Material, MaterialSection, Topic
from app.schemas import MaterialNoteIn, MaterialOut, MaterialTextOut, SectionAssignIn, SectionOut, UnsortedSectionOut
from app.services import content, ingestion
from app.services.materials import (
    ALLOWED_TYPES,
    delete_stored_file,
    inline_allowed,
    stored_path,
    store_upload,
)

router = APIRouter(tags=["materials"])


def _check_topic(db: DbSession, subject_id: int, topic_id: int | None) -> None:
    if topic_id is None:
        return
    topic = db.get(Topic, topic_id)
    if topic is None or topic.subject_id != subject_id:
        raise bad_request("invalid_topic", "The topic does not belong to this subject.")


def _own_material(db: DbSession, user_id: int, material_id: int) -> Material:
    material = db.scalar(select(Material).where(Material.id == material_id, Material.uploader_id == user_id))
    if material is None:
        raise not_found("Material")
    return material


@router.get("/subjects/{subject_id}/materials", response_model=list[MaterialOut])
def list_materials(subject_id: int, user: CurrentUser, db: DbSession, topic_id: int | None = None) -> list[Material]:
    content.get_visible_subject(db, user, subject_id)
    query = select(Material).where(Material.subject_id == subject_id, Material.uploader_id == user.id)
    if topic_id is not None:
        query = query.where(Material.topic_id == topic_id)
    return list(db.scalars(query.order_by(Material.created_at.desc())).all())


@router.post("/materials/upload", response_model=MaterialOut, status_code=201)
async def upload_material(
    user: CurrentUser,
    db: DbSession,
    subject_id: Annotated[int, Form()],
    file: Annotated[UploadFile, File()],
    topic_id: Annotated[int | None, Form()] = None,
    title: Annotated[str | None, Form(max_length=200)] = None,
) -> Material:
    content.get_visible_subject(db, user, subject_id)
    _check_topic(db, subject_id, topic_id)
    upload_limiter.hit(user.id)
    stored_name, original_name, mime_type = await store_upload(file)
    material = Material(
        subject_id=subject_id,
        topic_id=topic_id,
        title=(title or "").strip() or original_name,
        kind="file",
        stored_name=stored_name,
        original_name=original_name,
        mime_type=mime_type,
        uploader_id=user.id,
    )
    db.add(material)
    try:
        db.commit()
    except Exception:
        db.rollback()
        delete_stored_file(stored_name)
        raise
    await run_in_threadpool(ingestion.extract_material, db, material)
    db.commit()
    return material


@router.post("/materials/note", response_model=MaterialOut, status_code=201)
def create_note(payload: MaterialNoteIn, user: CurrentUser, db: DbSession) -> Material:
    content.get_visible_subject(db, user, payload.subject_id)
    _check_topic(db, payload.subject_id, payload.topic_id)
    material = Material(
        subject_id=payload.subject_id,
        topic_id=payload.topic_id,
        title=payload.title,
        kind=payload.kind,
        body=payload.body,
        uploader_id=user.id,
    )
    db.add(material)
    db.flush()
    ingestion.extract_material(db, material)
    db.commit()
    return material


@router.get("/materials/{material_id}/file")
def download_material(material_id: int, user: CurrentUser, db: DbSession) -> FileResponse:
    material = _own_material(db, user.id, material_id)
    if material.kind != "file" or not material.stored_name:
        raise not_found("File")
    path = stored_path(material.stored_name)
    if not path.is_file():
        raise not_found("File")
    extension = Path(material.stored_name).suffix.lower()
    media_type = ALLOWED_TYPES[extension][0]
    return FileResponse(
        path,
        media_type=media_type,
        filename=material.original_name,
        content_disposition_type="inline" if inline_allowed(extension) else "attachment",
        headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox"},
    )


@router.delete("/materials/{material_id}", status_code=204)
def delete_material(material_id: int, user: CurrentUser, db: DbSession) -> None:
    material = _own_material(db, user.id, material_id)
    stored_name = material.stored_name
    db.delete(material)
    db.commit()
    delete_stored_file(stored_name)


@router.get("/materials/{material_id}/text", response_model=MaterialTextOut)
def material_text(material_id: int, user: CurrentUser, db: DbSession) -> Material:
    return _own_material(db, user.id, material_id)


@router.post("/materials/{material_id}/extract", response_model=MaterialOut)
async def reextract_material(material_id: int, user: CurrentUser, db: DbSession) -> Material:
    material = _own_material(db, user.id, material_id)
    if not ingestion.extractable(material):
        raise bad_request("not_extractable", "Text cannot be read from this material yet.")
    extract_limiter.hit(user.id)
    await run_in_threadpool(ingestion.extract_material, db, material)
    db.commit()
    return material


@router.get("/materials/{material_id}/sections", response_model=list[SectionOut])
def material_sections(material_id: int, user: CurrentUser, db: DbSession) -> list[MaterialSection]:
    return list(_own_material(db, user.id, material_id).sections)


@router.put("/materials/{material_id}/sections/{section_id}", response_model=SectionOut)
def assign_section(
    material_id: int, section_id: int, payload: SectionAssignIn, user: CurrentUser, db: DbSession
) -> MaterialSection:
    material = _own_material(db, user.id, material_id)
    section = db.scalar(
        select(MaterialSection).where(MaterialSection.id == section_id, MaterialSection.material_id == material.id)
    )
    if section is None:
        raise not_found("Section")
    _check_topic(db, material.subject_id, payload.topic_id)
    section.topic_id, section.assigned_by = payload.topic_id, "student"
    db.commit()
    return section


@router.get("/subjects/{subject_id}/unsorted", response_model=list[UnsortedSectionOut])
def unsorted_sections(subject_id: int, user: CurrentUser, db: DbSession) -> list[UnsortedSectionOut]:
    content.get_visible_subject(db, user, subject_id)
    rows = db.execute(
        select(MaterialSection, Material.title)
        .join(Material, Material.id == MaterialSection.material_id)
        .where(
            Material.subject_id == subject_id,
            Material.uploader_id == user.id,
            MaterialSection.topic_id.is_(None),
            MaterialSection.word_count > 0,
        )
        .order_by(Material.created_at.desc(), MaterialSection.position)
    ).all()
    return [
        UnsortedSectionOut(**SectionOut.model_validate(section).model_dump(), material_title=title)
        for section, title in rows
    ]
