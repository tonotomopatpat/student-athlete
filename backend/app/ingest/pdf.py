"""PDF text layer to blocks. Headings come from font size and weight; repeated headers and footers are dropped."""

import re
import statistics
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.ingest.document import Block, Document, IngestError
from app.ingest.limits import MAX_PAGES, MIN_CHARS_PER_PAGE

BULLET_START = re.compile(r"^\s*(?:[•▪●◦‣■□➢✓\-–*]|\uf0b7|\uf0a7)\s*")
PAGE_NUMBER = re.compile(r"^(?:page\s*)?\d{1,4}(?:\s*(?:of|/)\s*\d{1,4})?$", re.IGNORECASE)
HEADING_RATIO = 1.15
MAX_HEADING_WORDS = 14


@dataclass
class Line:
    text: str = ""
    size: float = 0.0
    y: float = 0.0
    bold_chars: int = 0
    chars: int = 0
    bold_spans: list[str] = field(default_factory=list)

    @property
    def bold(self) -> bool:
        return self.chars > 0 and self.bold_chars >= 0.9 * self.chars


def _font_is_bold(font_dict) -> bool:  # noqa: ANN001
    if not font_dict:
        return False
    name = str(font_dict.get("/BaseFont", "")).lower()
    return any(mark in name for mark in ("bold", "black", "heavy", "semibold"))


def _page_lines(page) -> list[Line]:  # noqa: ANN001
    lines: list[Line] = [Line()]

    def visitor(text: str, cm: list, tm: list, font_dict, font_size: float) -> None:  # noqa: ANN001
        if not text:
            return
        scale = abs(tm[3] * cm[3]) if tm and cm else 1.0
        size = round(font_size * (scale or 1.0), 1)
        y = tm[5] * cm[3] + cm[5] if tm and cm else 0.0
        bold = _font_is_bold(font_dict)
        parts = text.split("\n")
        for index, part in enumerate(parts):
            current = lines[-1]
            if index > 0 or (current.chars and abs(y - current.y) > max(current.size, size) * 0.6):
                current = Line(y=y)
                lines.append(current)
            if not part:
                continue
            if not current.chars:
                current.y = y
            visible = len(part.strip())
            current.text += part
            current.chars += visible
            current.size = max(current.size, size) if visible else current.size
            if bold and visible:
                current.bold_chars += visible
                current.bold_spans.append(part.strip())

    page.extract_text(visitor_text=visitor)
    cleaned = []
    for line in lines:
        line.text = re.sub(r"\s+", " ", line.text).strip()
        if line.text:
            cleaned.append(line)
    return cleaned


def _normalize_repeat(text: str) -> str:
    return re.sub(r"\d+", "#", text.lower()).strip()


def _drop_running_heads(pages: list[list[Line]]) -> None:
    if len(pages) < 3:
        return
    edge_counts: Counter[str] = Counter()
    for lines in pages:
        edges = {_normalize_repeat(line.text) for line in lines[:2] + lines[-2:]}
        edge_counts.update(edges)
    repeated = {text for text, count in edge_counts.items() if count >= max(3, len(pages) * 0.5)}
    for lines in pages:
        lines[:] = [
            line for position, line in enumerate(lines)
            if not ((position < 2 or position >= len(lines) - 2) and _normalize_repeat(line.text) in repeated)
        ]


def _heading_levels(lines: list[Line], body_size: float) -> dict[float, int]:
    sizes = sorted(
        {line.size for line in lines if line.size >= body_size * HEADING_RATIO and len(line.text.split()) <= MAX_HEADING_WORDS},
        reverse=True,
    )
    return {size: min(index + 1, 4) for index, size in enumerate(sizes)}


def _emphasis(line: Line) -> list[str]:
    spans = [span for span in line.bold_spans if 2 <= len(span) <= 60]
    return list(dict.fromkeys(spans))[:8]


def _lines_to_blocks(pages: list[list[Line]], document: Document) -> None:
    all_lines = [line for lines in pages for line in lines]
    if not all_lines:
        return
    weighted = [line.size for line in all_lines for _ in range(max(1, line.chars // 20))]
    body_size = statistics.median(weighted)
    levels = _heading_levels(all_lines, body_size)
    deepest = max(levels.values(), default=0)
    for page_number, lines in enumerate(pages, start=1):
        paragraph: list[Line] = []

        def flush() -> None:
            if paragraph:
                text = " ".join(line.text for line in paragraph)
                text = re.sub(r"(\w)- (\w)", lambda m: m.group(1) + m.group(2) if m.group(2).islower() else m.group(0), text)
                spans = [span for line in paragraph for span in _emphasis(line)]
                document.blocks.append(Block("paragraph", text, page=page_number, emphasis=spans[:12]))
                paragraph.clear()

        for line in lines:
            if PAGE_NUMBER.match(line.text):
                continue
            words = len(line.text.split())
            terminal = line.text.endswith((".", ";", ","))
            if line.size in levels and not terminal:
                flush()
                document.blocks.append(Block("heading", line.text, levels[line.size], page_number))
                continue
            if line.bold and words <= 10 and not terminal and line.size >= body_size * 0.95:
                flush()
                document.blocks.append(Block("heading", line.text, min(deepest + 1, 5), page_number))
                continue
            if BULLET_START.match(line.text):
                flush()
                text = BULLET_START.sub("", line.text, count=1)
                document.blocks.append(Block("list_item", text, page=page_number, emphasis=_emphasis(line)))
                continue
            previous = paragraph[-1] if paragraph else None
            gap = abs(previous.y - line.y) if previous else 0.0
            if previous and gap > max(previous.size, line.size) * 1.9:
                flush()
            elif not previous and document.blocks and document.blocks[-1].kind == "list_item" \
                    and document.blocks[-1].page == page_number and line.text[:1].islower():
                document.blocks[-1].text += " " + line.text
                continue
            paragraph.append(line)
        flush()


def parse_pdf(path: Path) -> Document:
    try:
        reader = PdfReader(str(path), strict=False)
        if reader.is_encrypted and not reader.decrypt(""):
            raise IngestError("encrypted", "This PDF is password-protected.")
        page_count = len(reader.pages)
    except IngestError:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError, OSError) as error:
        raise IngestError("unreadable", "This PDF could not be read.") from error
    if page_count > MAX_PAGES:
        raise IngestError("too_many_pages", f"PDFs can have at most {MAX_PAGES} pages.")
    document = Document(format="pdf", page_count=page_count)
    pages: list[list[Line]] = []
    for page in reader.pages:
        try:
            pages.append(_page_lines(page))
        except Exception:  # noqa: BLE001  (one broken page should not lose the rest)
            pages.append([])
            document.warnings.append("page_unreadable")
    _drop_running_heads(pages)
    _lines_to_blocks(pages, document)
    if page_count and document.char_count() < MIN_CHARS_PER_PAGE * page_count * 0.5:
        document.warnings.append("no_text_layer")
    return document
