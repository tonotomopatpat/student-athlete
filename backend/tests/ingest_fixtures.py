"""Builders for small synthetic documents used by the ingestion tests (never used as evidence of quality)."""

import io
import zipfile

from docx import Document as new_docx
from pptx import Presentation
from pptx.util import Inches

Line = tuple[str, float, bool]


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(pages: list[list[Line]]) -> bytes:
    """A valid PDF whose pages hold the given (text, font size, bold) lines, top to bottom."""
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"",  # pages tree, filled below
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
    ]
    page_ids = []
    for lines in pages:
        y = 760.0
        ops = []
        for text, size, bold in lines:
            ops.append(f"BT /{'F2' if bold else 'F1'} {size} Tf 72 {y:.1f} Td ({_escape(text)}) Tj ET")
            y -= size * 1.5
        stream = "\n".join(ops).encode("latin-1")
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        content_id = len(objects)
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
            b"/Contents %d 0 R >>" % content_id
        )
        page_ids.append(len(objects))
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids).encode()
    objects[1] = b"<< /Type /Pages /Kids [" + kids + b"] /Count %d >>" % len(page_ids)
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % number + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for offset in offsets:
        out.write(b"%010d 00000 n \n" % offset)
    out.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref))
    return out.getvalue()


def make_docx(build) -> bytes:  # noqa: ANN001
    document = new_docx()
    build(document)
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


def make_pptx(slides: list[tuple[str, list[tuple[str, int]], str]]) -> bytes:
    """Slides of (title, [(bullet text, level)], speaker notes)."""
    deck = Presentation()
    for title, bullets, notes in slides:
        slide = deck.slides.add_slide(deck.slide_layouts[1])
        slide.shapes.title.text = title
        body = slide.placeholders[1].text_frame
        for index, (text, level) in enumerate(bullets):
            paragraph = body.paragraphs[0] if index == 0 else body.add_paragraph()
            paragraph.text = text
            paragraph.level = level
        if notes:
            slide.notes_slide.notes_text_frame.text = notes
    box = deck.slides[0].shapes.add_textbox(Inches(1), Inches(6), Inches(4), Inches(1))
    box.text_frame.text = "Source: class handout"
    out = io.BytesIO()
    deck.save(out)
    return out.getvalue()


def rewrite_zip(data: bytes, replace: dict[str, bytes] | None = None, extra: dict[str, bytes] | None = None) -> bytes:
    source = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            target.writestr(item.filename, (replace or {}).get(item.filename, source.read(item.filename)))
        for name, body in (extra or {}).items():
            target.writestr(name, body)
    return out.getvalue()


BILLION_LAUGHS = (
    b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;">]>'
    b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r>'
    b"<w:t>&lol2;</w:t></w:r></w:p></w:body></w:document>"
)
