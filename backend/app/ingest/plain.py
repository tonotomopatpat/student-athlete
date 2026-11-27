"""Plain text and the stored markup form.

Extracted lessons are stored as light markup so that structure survives editing:
    [page 3]            page or slide boundary
    ## Title            heading (number of # = level)
    - item / 1. item    list item (two spaces of indent per level)
    | a | b |           table row
    > text              speaker note
    **term**            emphasized term
Paragraphs are separated by blank lines. Raw .txt uploads go through the same parser.
"""

import re

from app.ingest.document import Block, Document

PAGE_MARKER = re.compile(r"^\[(page|slide)\s+(\d+)\]$", re.IGNORECASE)
HEADING = re.compile(r"^(#{1,6})\s+(.+)$")
BULLET = re.compile(r"^(\s*)(?:[-*•▪●◦‣–]|\(?\d{1,2}[.)]|\(?[a-hA-H][.)])\s+(.+)$")
TABLE_ROW = re.compile(r"^\|(.+)\|$")
NOTE = re.compile(r"^>\s?(.*)$")
KEY_VALUE = re.compile(r"^[A-Z][\w ./&()'-]{1,40}:\s+\S")
EMPHASIS = re.compile(r"\*\*(.+?)\*\*")
NUMBERED_HEADING = re.compile(
    r"^(?:(?:chapter|unit|week|lesson|module|topic|part)\s+(?:\d+|[IVXLC]+)\b|\d+(?:\.\d+)+\.?\s+\S)", re.IGNORECASE
)
TERMINAL = (".", "?", "!", ";", ",", ":")


def decode_text(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def _strip_emphasis(text: str) -> tuple[str, list[str]]:
    spans = [span.strip() for span in EMPHASIS.findall(text) if span.strip()]
    return EMPHASIS.sub(r"\1", text), spans


def _looks_like_heading(line: str, previous_blank: bool, next_blank: bool) -> int:
    """Heading level for an unmarked line of raw text, or 0 if it reads like body text."""
    words = line.split()
    if not words or len(words) > 12 or line.endswith(TERMINAL) or len(line) > 90:
        return 0
    if NUMBERED_HEADING.match(line):
        number = re.match(r"^(\d+(?:\.\d+)*)", line)
        return min(number.group(1).count(".") + 1, 4) if number else 1
    if not (previous_blank and next_blank):
        return 0
    letters = [ch for ch in line if ch.isalpha()]
    if len(letters) >= 3 and all(ch.isupper() for ch in letters):
        return 1
    capitalized = sum(1 for word in words if word[:1].isupper() or not word[:1].isalpha())
    return 2 if capitalized / len(words) >= 0.7 else 0


def _join_lines(lines: list[str]) -> str:
    text = ""
    for line in lines:
        line = line.strip()
        if text.endswith("-") and line[:1].islower() and len(text) > 1 and text[-2].isalpha():
            text = text[:-1] + line
        else:
            text = f"{text} {line}" if text else line
    return re.sub(r"\s+", " ", text)


def parse_text(text: str, format: str = "txt") -> Document:
    document = Document(format=format)
    lines = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ").split("\n")
    page: int | None = None
    paragraph: list[str] = []

    def add(kind: str, raw: str, level: int = 0) -> None:
        clean, spans = _strip_emphasis(raw.strip())
        if clean:
            document.blocks.append(Block(kind=kind, text=clean, level=level, page=page, emphasis=spans))

    def flush() -> None:
        if paragraph:
            add("paragraph", _join_lines(paragraph))
            paragraph.clear()

    for index, raw_line in enumerate(lines):
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            flush()
            continue
        if marker := PAGE_MARKER.match(stripped):
            flush()
            document.page_label = marker.group(1).lower()
            page = int(marker.group(2))
            document.page_count = max(document.page_count, page)
            continue
        if heading := HEADING.match(stripped):
            flush()
            add("heading", heading.group(2), len(heading.group(1)))
            continue
        if note := NOTE.match(stripped):
            flush()
            add("note", note.group(1))
            continue
        if row := TABLE_ROW.match(stripped):
            flush()
            add("table_row", " | ".join(cell.strip() for cell in row.group(1).split("|")))
            continue
        previous_blank = index == 0 or not lines[index - 1].strip()
        next_blank = index + 1 >= len(lines) or not lines[index + 1].strip()
        if KEY_VALUE.match(stripped) and len(stripped) <= 200:
            flush()
            add("paragraph", stripped)
            continue
        if not paragraph and (level := _looks_like_heading(stripped, previous_blank, next_blank)):
            add("heading", stripped, level)
            continue
        if bullet := BULLET.match(line):
            flush()
            add("list_item", bullet.group(2), len(bullet.group(1).replace("\t", "  ")) // 2)
            continue
        if document.blocks and document.blocks[-1].kind == "list_item" and not paragraph and raw_line[:1] == " ":
            document.blocks[-1].text = _join_lines([document.blocks[-1].text, stripped])
            continue
        paragraph.append(stripped)
    flush()
    return document


def _with_emphasis(block: Block) -> str:
    text = block.text
    for span in block.emphasis:
        if span and span in text and f"**{span}**" not in text:
            text = text.replace(span, f"**{span}**", 1)
    return text


def to_markup(document: Document) -> str:
    out: list[str] = []
    page: int | None = None
    for block in document.blocks:
        if block.page is not None and block.page != page:
            page = block.page
            out.append(f"[{document.page_label} {page}]")
        text = _with_emphasis(block)
        if block.kind == "heading":
            out.append(f"{'#' * max(1, min(block.level or 1, 6))} {text}")
        elif block.kind == "list_item":
            out.append(f"{'  ' * block.level}- {text}")
        elif block.kind == "table_row":
            out.append(f"| {text} |")
        elif block.kind == "note":
            out.append(f"> {text}")
        else:
            out.append(text)
    return "\n\n".join(out) + ("\n" if out else "")
