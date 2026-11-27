"""Outline of a document: sections from headings, numbering ("1.", "1.1", "Week 3", "Unit II") and slide titles."""

import re
from dataclasses import dataclass, field

from app.ingest.document import Block, Document

NUMBERING = re.compile(
    r"^(?:(?P<word>chapter|unit|week|lesson|module|topic|part|session|section)\s*(?P<wnum>\d+|[ivxlc]+)\b"
    r"|(?P<num>\d+(?:\.\d+)*))\s*(?P<punct>[.):\-–—]*)\s*(?P<rest>.*)$",
    re.IGNORECASE,
)


@dataclass
class Section:
    title: str
    level: int
    number: str | None = None
    page: int | None = None
    blocks: list[Block] = field(default_factory=list)

    def body_text(self) -> str:
        return "\n".join(block.text for block in self.blocks)


def split_numbering(text: str) -> tuple[str | None, str]:
    """('1.2', 'Cell structure') for '1.2 Cell structure'; (None, text) when there is no numbering."""
    match = NUMBERING.match(text.strip())
    if not match:
        return None, text.strip()
    rest = match.group("rest").strip()
    if match.group("word"):
        number = f"{match.group('word').title()} {match.group('wnum').upper() if not match.group('wnum').isdigit() else match.group('wnum')}"
        return number, rest
    number = match.group("num")
    bare = "." not in number and not match.group("punct")
    if not rest[:1].isalpha() or len(number.split(".")[0]) > 2 or (bare and not rest[:1].isupper()):
        return None, text.strip()
    return number, rest


def outline(document: Document) -> list[Section]:
    sections: list[Section] = []
    current = Section(title="", level=0)
    for block in document.blocks:
        if block.kind == "heading":
            if current.title or current.blocks:
                sections.append(current)
            number, title = split_numbering(block.text)
            level = block.level or 1
            if number and number[:1].isdigit():
                level = number.count(".") + 1
            current = Section(title=title or block.text, level=level, number=number, page=block.page)
        else:
            current.blocks.append(block)
    if current.title or current.blocks:
        sections.append(current)
    return sections
