"""A parsed lesson or syllabus: an ordered list of typed blocks, with page or slide numbers."""

from dataclasses import asdict, dataclass, field
from typing import Literal

BlockKind = Literal["heading", "paragraph", "list_item", "table_row", "note"]


class IngestError(Exception):
    """A file that cannot or must not be parsed. `code` is safe to show to the student."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Block:
    kind: BlockKind
    text: str
    level: int = 0
    page: int | None = None
    emphasis: list[str] = field(default_factory=list)


@dataclass
class Document:
    format: str
    blocks: list[Block] = field(default_factory=list)
    page_count: int = 0
    page_label: str = "page"
    warnings: list[str] = field(default_factory=list)

    def plain_text(self) -> str:
        return "\n".join(block.text for block in self.blocks)

    def char_count(self) -> int:
        return sum(len(block.text) for block in self.blocks)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Document":
        blocks = [Block(**block) for block in data.get("blocks", [])]
        return cls(
            format=data["format"],
            blocks=blocks,
            page_count=data.get("page_count", 0),
            page_label=data.get("page_label", "page"),
            warnings=list(data.get("warnings", [])),
        )
