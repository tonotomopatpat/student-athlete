"""Syllabus to a proposed subject name, course code and ordered topic list. The student confirms before anything is saved."""

import re
from dataclasses import dataclass, field

from app.ingest.document import Block, Document
from app.ingest.structure import split_numbering
from app.nlp.tokens import content_stems

MAX_TOPICS = 40
MAX_NAME_LENGTH = 160
MIN_TOPICS = 3

NAME_LABEL = re.compile(
    r"^(?:course|subject)?\s*(?:descriptive\s+)?(?:title|name)\s*(?:of\s+the\s+course)?\s*[:|]\s*(?P<value>.+)$|"
    r"^(?:course|subject)\s*[:|]\s*(?P<value2>.+)$",
    re.IGNORECASE,
)
CODE_LABEL = re.compile(r"(?:course|subject)\s*(?:code|no\.?|number)\s*[:|]\s*(?P<code>[A-Za-z]{2,8}[\s\-]?\d{1,4}[A-Za-z]?)", re.IGNORECASE)
OUTLINE_START = re.compile(
    r"\b(course\s+(outline|content|contents|plan|calendar|schedule|map|coverage)|learning\s+plan|weekly\s+(schedule|plan|topics)"
    r"|topics?\s+(outline|covered)?|content\s+outline|subject\s+matter|scope\s+and\s+sequence|lesson\s+plan|course\s+topics)\b",
    re.IGNORECASE,
)
OUTLINE_END = re.compile(
    r"^(grading|grading\s+system|course\s+requirements|requirements|references|bibliography|suggested\s+readings"
    r"|textbooks?|class\s+policies|policies|evaluation|course\s+outcomes?|learning\s+outcomes?|prepared\s+by|approved\s+by)\b",
    re.IGNORECASE,
)
GENERIC_TITLE = re.compile(
    r"(syllabus|university|college|school|department|institute|office|republic|semester|academic\s+year|vision|mission)",
    re.IGNORECASE,
)
NOT_A_TOPIC = re.compile(
    r"^(?:(?:prelim|preliminary|midterm|mid-term|semi-?final|final|finals)(?:\s+(?:exam|examination|period|term|test|grading))?"
    r"|(?:long\s+)?(?:exam|examination|quiz|test)s?(?:\s+\d+)?|orientation.*|course\s+orientation.*|holiday.*|no\s+class(?:es)?.*"
    r"|(?:semester\s+)?break|review|consultation.*|submission.*|culminating.*|class\s+orientation.*|week|topics?|contents?"
    r"|learning\s+outcomes?|activities|assessment.*|date|time|remarks|references?)$",
    re.IGNORECASE,
)
TOPIC_HEADER = re.compile(r"\b(topic|topics|content|contents|subject\s+matter|lesson|lessons|coverage)\b", re.IGNORECASE)
DATE_PREFIX = re.compile(
    r"^(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s*\d{1,2}(?:\s*[-–]\s*\d{1,2})?,?\s*)+",
    re.IGNORECASE,
)
DURATION_SUFFIX = re.compile(r"\s*[\(\[]?\s*\d+(?:\.\d+)?\s*(?:hrs?|hours?|mins?|minutes?|wks?|weeks?)\s*[\)\]]?\s*$", re.IGNORECASE)
WEEK_PREFIX = re.compile(r"^(?:weeks?|wk)\s*\d+(?:\s*[-–&,]\s*\d+)*\s*[:.\-–]?\s*", re.IGNORECASE)


@dataclass
class SyllabusProposal:
    name: str
    code: str | None
    topics: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _cells(block: Block) -> list[str]:
    return [cell.strip() for cell in block.text.split(" | ")] if block.kind == "table_row" else [block.text]


def _find_name_and_code(blocks: list[Block]) -> tuple[str | None, str | None]:
    name = code = None
    for block in blocks[:80]:
        cells = _cells(block)
        joined = " | ".join(cells)
        if code is None and (match := CODE_LABEL.search(joined)):
            code = re.sub(r"\s+", " ", match.group("code")).upper()
        if name is None:
            for index, cell in enumerate(cells):
                if match := NAME_LABEL.match(cell):
                    value = (match.group("value") or match.group("value2") or "").strip()
                    if value:
                        name = value
                        break
                label = cell.lower().rstrip(":").strip()
                if label in ("course title", "descriptive title", "subject title", "course name", "subject", "course") \
                        and index + 1 < len(cells) and cells[index + 1]:
                    name = cells[index + 1]
                    break
    if name is None:
        for block in blocks[:25]:
            if block.kind == "heading" and 3 <= len(block.text) <= MAX_NAME_LENGTH \
                    and not GENERIC_TITLE.search(block.text) and not OUTLINE_START.search(block.text):
                name = block.text
                break
    if name:
        name = re.sub(r"\s+", " ", name).strip(" :|-")
        if code and name.upper().startswith(code):
            name = name[len(code):].strip(" :-–")
    return (name[:MAX_NAME_LENGTH] if name else None), code


def _outline_region(blocks: list[Block]) -> list[Block]:
    start = next(
        (index for index, block in enumerate(blocks)
         if block.kind in ("heading", "paragraph", "table_row") and len(block.text) <= 80 and OUTLINE_START.search(block.text)),
        None,
    )
    if start is None:
        return blocks
    region = []
    for block in blocks[start + 1:]:
        if block.kind in ("heading", "paragraph") and len(block.text) <= 60 and OUTLINE_END.match(block.text):
            break
        region.append(block)
    return region or blocks


def clean_topic(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip(" -–•*:;|")
    text = DATE_PREFIX.sub("", text)
    text = WEEK_PREFIX.sub("", text)
    number, rest = split_numbering(text)
    if number:
        text = rest
    text = DURATION_SUFFIX.sub("", text).strip(" -–:;.,|")
    if len(text) > 120:
        first = re.split(r"(?<=[.;])\s", text, maxsplit=1)[0]
        text = first if len(first) <= 120 else text[:117].rsplit(" ", 1)[0]
    return text.strip(" -–:;.,")


def _is_topic(text: str) -> bool:
    letters = sum(ch.isalpha() for ch in text)
    return letters >= 3 and len(text) <= MAX_NAME_LENGTH and not NOT_A_TOPIC.match(text.strip())


def _table_topics(rows: list[Block]) -> list[str]:
    topic_column: int | None = None
    topics: list[str] = []
    for row in rows:
        cells = _cells(row)
        if topic_column is None:
            for index, cell in enumerate(cells):
                if len(cell) <= 40 and TOPIC_HEADER.search(cell):
                    topic_column = index
                    break
            if topic_column is not None:
                continue
        if topic_column is not None and topic_column < len(cells):
            topics.append(cells[topic_column])
        elif len(cells) >= 2 and WEEK_PREFIX.match(cells[0] + " "):
            topics.append(cells[1])
    return topics


def _block_topics(region: list[Block]) -> list[str]:
    numbered: list[str] = []
    listed: list[tuple[int, str]] = []
    for index, block in enumerate(region):
        if block.kind == "table_row":
            continue
        number, rest = split_numbering(block.text)
        is_week = bool(WEEK_PREFIX.match(block.text))
        if number or is_week:
            if not rest and index + 1 < len(region) and region[index + 1].kind != "table_row":
                rest = region[index + 1].text
            numbered.append(rest if number else block.text)
        elif block.kind == "list_item":
            listed.append((block.level, block.text))
    if len(numbered) >= MIN_TOPICS:
        return numbered
    top_level = [text for level, text in listed if level == 0]
    if MIN_TOPICS <= len(top_level) <= MAX_TOPICS:
        return top_level
    return [text for _, text in listed] or numbered


def _dedupe(topics: list[str]) -> list[str]:
    kept: list[str] = []
    stems: list[set[str]] = []
    for topic in topics:
        current = set(content_stems(topic))
        duplicate = any(
            topic.lower() == other.lower() or (current and len(current & seen) / len(current | seen) >= 0.8)
            for other, seen in zip(kept, stems)
        )
        if not duplicate:
            kept.append(topic)
            stems.append(current)
    return kept


def propose_topics(document: Document) -> SyllabusProposal:
    name, code = _find_name_and_code(document.blocks)
    region = _outline_region(document.blocks)
    rows = [block for block in region if block.kind == "table_row"]
    raw = _table_topics(rows) if len(rows) >= MIN_TOPICS else []
    if len(raw) < MIN_TOPICS:
        raw = _block_topics(region)
    topics = _dedupe([topic for topic in (clean_topic(item) for item in raw) if _is_topic(topic)])[:MAX_TOPICS]
    proposal = SyllabusProposal(name=name or "", code=code, topics=topics)
    if not name:
        proposal.warnings.append("no_name_found")
    if not topics:
        proposal.warnings.append("no_topics_found")
    elif len(topics) < MIN_TOPICS:
        proposal.warnings.append("few_topics")
    return proposal
