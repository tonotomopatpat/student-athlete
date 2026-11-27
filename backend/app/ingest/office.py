"""DOCX and PPTX to blocks. The zip container and every XML part are vetted before python-docx/pptx open them."""

import zipfile
from pathlib import Path

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import ParseError
from defusedxml.ElementTree import fromstring as safe_fromstring
from docx import Document as open_docx
from docx.table import Table
from docx.text.paragraph import Paragraph
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE, PP_PLACEHOLDER

from app.ingest.document import Block, Document, IngestError
from app.ingest.limits import (
    MAX_PAGES,
    MAX_XML_PART_BYTES,
    MAX_ZIP_ENTRIES,
    MAX_ZIP_RATIO,
    MAX_ZIP_UNCOMPRESSED_BYTES,
)

BODY_PLACEHOLDERS = {PP_PLACEHOLDER.BODY, PP_PLACEHOLDER.OBJECT, PP_PLACEHOLDER.SUBTITLE}
TITLE_PLACEHOLDERS = {PP_PLACEHOLDER.TITLE, PP_PLACEHOLDER.CENTER_TITLE, PP_PLACEHOLDER.VERTICAL_TITLE}


def vet_office_zip(path: Path, required_part: str) -> None:
    try:
        archive = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as error:
        raise IngestError("unreadable", "This file is not a valid Office document.") from error
    with archive:
        entries = archive.infolist()
        if len(entries) > MAX_ZIP_ENTRIES:
            raise IngestError("too_complex", "This document has too many internal parts.")
        if sum(entry.file_size for entry in entries) > MAX_ZIP_UNCOMPRESSED_BYTES:
            raise IngestError("too_large", "This document expands to more data than allowed.")
        if required_part not in {entry.filename for entry in entries}:
            raise IngestError("unreadable", "This file is not a valid Office document.")
        for entry in entries:
            if entry.file_size > 1024 * 1024 and entry.file_size > MAX_ZIP_RATIO * max(entry.compress_size, 1):
                raise IngestError("too_large", "This document is compressed suspiciously well and was rejected.")
            if not entry.filename.endswith((".xml", ".rels")):
                continue
            if entry.file_size > MAX_XML_PART_BYTES:
                raise IngestError("too_large", "A part of this document is too large.")
            try:
                safe_fromstring(archive.read(entry), forbid_dtd=True, forbid_entities=True, forbid_external=True)
            except (DefusedXmlException, ParseError, zipfile.BadZipFile) as error:
                raise IngestError("unsafe_document", "This document contains content that is not allowed.") from error


def _bold_spans(runs) -> list[str]:  # noqa: ANN001
    spans: list[str] = []
    current = ""
    for run in runs:
        if run.font.bold:
            current += run.text
        elif current:
            spans.append(current.strip())
            current = ""
    if current:
        spans.append(current.strip())
    return [span for span in spans if 2 <= len(span) <= 60][:8]


def _docx_paragraph(paragraph: Paragraph) -> Block | None:
    text = " ".join(paragraph.text.split())
    if not text:
        return None
    style = (paragraph.style.name if paragraph.style is not None else "") or ""
    spans = _bold_spans(paragraph.runs)
    if style == "Title":
        return Block("heading", text, 1)
    if style.startswith("Heading"):
        digits = "".join(ch for ch in style if ch.isdigit())
        return Block("heading", text, min(int(digits or 1), 6))
    properties = paragraph._p.pPr
    numbered = properties is not None and properties.numPr is not None
    if numbered or "List" in style:
        level = 0
        if numbered and properties.numPr.ilvl is not None:
            level = int(properties.numPr.ilvl.val)
        return Block("list_item", text, level, emphasis=spans)
    all_bold = spans and sum(len(span) for span in spans) >= 0.9 * len(text.replace(" ", "")) - 2
    if all_bold and len(text.split()) <= 10 and not text.endswith((".", ";", ",")):
        return Block("heading", text, 3)
    return Block("paragraph", text, emphasis=spans)


def parse_docx(path: Path) -> Document:
    vet_office_zip(path, "word/document.xml")
    try:
        source = open_docx(str(path))
    except Exception as error:  # noqa: BLE001  (python-docx raises many types for corrupt files)
        raise IngestError("unreadable", "This Word document could not be read.") from error
    document = Document(format="docx")
    for element in source.element.body.iterchildren():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag == "p":
            if block := _docx_paragraph(Paragraph(element, source)):
                document.blocks.append(block)
        elif tag == "tbl":
            for row in Table(element, source).rows:
                cells = list(dict.fromkeys(" ".join(cell.text.split()) for cell in row.cells))
                text = " | ".join(cell for cell in cells if cell)
                if text:
                    document.blocks.append(Block("table_row", text))
    return document


def _shape_blocks(shape, slide_number: int, blocks: list[Block]) -> None:  # noqa: ANN001
    if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
        for child in sorted(shape.shapes, key=lambda s: ((s.top or 0), (s.left or 0))):
            _shape_blocks(child, slide_number, blocks)
        return
    if getattr(shape, "has_table", False) and shape.has_table:
        for row in shape.table.rows:
            text = " | ".join(" ".join(cell.text.split()) for cell in row.cells if cell.text.strip())
            if text:
                blocks.append(Block("table_row", text, page=slide_number))
        return
    if not getattr(shape, "has_text_frame", False) or not shape.has_text_frame:
        return
    placeholder = shape.placeholder_format.type if shape.is_placeholder else None
    if placeholder in TITLE_PLACEHOLDERS:
        return
    as_list = placeholder in BODY_PLACEHOLDERS
    for paragraph in shape.text_frame.paragraphs:
        text = " ".join(paragraph.text.split())
        if not text:
            continue
        spans = _bold_spans(paragraph.runs)
        kind = "list_item" if as_list or paragraph.level > 0 else "paragraph"
        blocks.append(Block(kind, text, paragraph.level, slide_number, spans))


def parse_pptx(path: Path) -> Document:
    vet_office_zip(path, "ppt/presentation.xml")
    try:
        deck = Presentation(str(path))
    except Exception as error:  # noqa: BLE001
        raise IngestError("unreadable", "This PowerPoint file could not be read.") from error
    if len(deck.slides) > MAX_PAGES:
        raise IngestError("too_many_pages", f"Presentations can have at most {MAX_PAGES} slides.")
    document = Document(format="pptx", page_count=len(deck.slides), page_label="slide")
    for number, slide in enumerate(deck.slides, start=1):
        title_shape = slide.shapes.title
        title = " ".join(title_shape.text_frame.text.split()) if title_shape is not None and title_shape.has_text_frame else ""
        if title:
            document.blocks.append(Block("heading", title, 2, number))
        body: list[Block] = []
        others = [shape for shape in slide.shapes if shape is not title_shape]
        for shape in sorted(others, key=lambda s: ((s.top or 0), (s.left or 0))):
            _shape_blocks(shape, number, body)
        document.blocks.extend(body)
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame is not None:
            notes = " ".join(slide.notes_slide.notes_text_frame.text.split())
            if notes:
                document.blocks.append(Block("note", notes, page=number))
    return document
