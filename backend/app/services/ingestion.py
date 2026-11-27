"""Material text extraction, outline sections and lesson-to-topic routing."""

import hashlib
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingest.document import Document, IngestError
from app.ingest.extract import extract_document, format_for
from app.ingest.plain import parse_text, to_markup
from app.ingest.routing import route_sections
from app.ingest.structure import outline
from app.models import Material, MaterialSection, Topic
from app.nlp.language import detect_language
from app.services.materials import stored_path

logger = logging.getLogger(__name__)


def extractable(material: Material) -> bool:
    if material.kind == "note":
        return True
    return material.kind == "file" and bool(material.stored_name) and format_for(material.stored_name) is not None


def _source_document(material: Material) -> Document:
    if material.kind == "note":
        return parse_text(material.body, "note")
    return extract_document(stored_path(material.stored_name), format_for(material.stored_name))


def apply_text(db: Session, material: Material, document: Document) -> None:
    markup = to_markup(document)
    material.extracted_text = markup
    material.text_hash = hashlib.sha256(markup.encode("utf-8")).hexdigest()
    material.language = detect_language(document.plain_text())
    if not document.blocks or "no_text_layer" in document.warnings:
        material.extraction_status, material.extraction_error = "needs_review", "no_text_layer"
    else:
        material.extraction_status = "ok"
        material.extraction_error = "truncated" if "truncated" in document.warnings else None
    rebuild_sections(db, material, document)


def extract_material(db: Session, material: Material) -> None:
    """Fill the material's text, status, language and sections. Bad files set a failed status instead of raising."""
    if not extractable(material):
        return
    try:
        document = _source_document(material)
    except IngestError as error:
        material.extraction_status, material.extraction_error = "failed", error.code
        material.extracted_text = material.text_hash = material.language = None
        material.sections.clear()
        return
    apply_text(db, material, document)
    logger.info("Extracted material %s: status=%s sections=%s", material.id, material.extraction_status, len(material.sections))


def material_document(material: Material) -> Document:
    return parse_text(material.extracted_text or "", "markup")


def rebuild_sections(db: Session, material: Material, document: Document | None = None) -> None:
    """Sync section rows with the outline in place, so ids stay stable and student choices survive re-routing."""
    sections = outline(document or material_document(material))
    topics = [tuple(row) for row in db.execute(
        select(Topic.id, Topic.name).where(Topic.subject_id == material.subject_id).order_by(Topic.position)
    ).all()]
    routes = route_sections(sections, topics, material.topic_id)
    existing = {row.position: row for row in material.sections}
    for position, (section, route) in enumerate(zip(sections, routes)):
        title = section.title[:300]
        row = existing.pop(position, None)
        if row is None:
            row = MaterialSection(position=position)
            material.sections.append(row)
        keep_choice = row.assigned_by == "student" and row.title == title
        row.title, row.level, row.page = title, section.level, section.page
        row.word_count = len(section.body_text().split())
        row.score = route.score
        if not keep_choice:
            row.topic_id, row.assigned_by = route.topic_id, "auto"
    for row in existing.values():
        material.sections.remove(row)


def reroute_subject(db: Session, subject_id: int) -> None:
    """Re-run routing for auto-assigned sections after the subject's topic list changes."""
    materials = db.scalars(
        select(Material).where(Material.subject_id == subject_id, Material.extraction_status.in_(("ok", "needs_review")))
    ).all()
    for material in materials:
        if material.extracted_text:
            rebuild_sections(db, material)
