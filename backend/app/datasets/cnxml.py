"""OpenStax CNXML module to our lesson markup, plus the module's marked key terms and glossary.

Exercises, solutions, figures, math and "link to learning" boxes are dropped: the corpus is prose only.
"""

import re
import xml.etree.ElementTree as ElementTree

from defusedxml.ElementTree import fromstring

CNX = "{http://cnx.rice.edu/cnxml}"
SKIP = {f"{CNX}{tag}" for tag in ("exercise", "solution", "problem", "figure", "media", "equation", "footnote",
                                   "code", "preformat", "commentary", "metadata", "image")}
SKIP_CLASSES = {"review-questions", "critical-thinking", "personal-application", "practice", "homework",
                "free-response", "multiple-choice", "references", "link-to-learning", "check-understanding",
                "section-exercises", "bringing-it-together", "solutions"}
BLOCK_TAGS = {f"{CNX}{tag}" for tag in ("para", "list", "table", "section", "note", "glossary", "title", "quote")}


def _classes(element: ElementTree.Element) -> set[str]:
    return set((element.get("class") or "").split())


def _skipped(element: ElementTree.Element) -> bool:
    if element.tag in SKIP or not element.tag.startswith(CNX):
        return True
    return bool(_classes(element) & SKIP_CLASSES)


def _inline(element: ElementTree.Element, terms: list[str]) -> str:
    parts = [element.text or ""]
    for child in element:
        if child.tag == f"{CNX}term":
            text = " ".join(_inline(child, []).split())
            if text:
                terms.append(text)
                parts.append(f"**{text}**")
        elif child.tag in BLOCK_TAGS or _skipped(child):
            parts.append(" ")
        else:
            parts.append(_inline(child, terms))
        parts.append(child.tail or "")
    return "".join(parts)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _read_glossary(element: ElementTree.Element, glossary: list[dict]) -> None:
    for definition in element.findall(f"{CNX}definition"):
        term, meaning = definition.find(f"{CNX}term"), definition.find(f"{CNX}meaning")
        if term is not None and meaning is not None:
            glossary.append({"term": _clean(_inline(term, [])), "meaning": _clean(_inline(meaning, []))})


def _walk(element: ElementTree.Element, depth: int, out: list[str], terms: list[str], glossary: list[dict]) -> None:
    for child in element:
        if _skipped(child):
            continue
        tag = child.tag[len(CNX):]
        if tag == "title":
            continue
        if tag == "section":
            title = child.find(f"{CNX}title")
            if title is not None and (heading := _clean(_inline(title, []))):
                out.append(f"{'#' * min(depth + 1, 6)} {heading}")
            _walk(child, depth + 1, out, terms, glossary)
        elif tag == "para":
            if text := _clean(_inline(child, terms)):
                out.append(text)
        elif tag == "list":
            for item in child.findall(f"{CNX}item"):
                if text := _clean(_inline(item, terms)):
                    out.append(f"- {text}")
        elif tag == "table":
            for row in child.iter(f"{CNX}row"):
                cells = [_clean(_inline(entry, terms)) for entry in row.findall(f"{CNX}entry")]
                if any(cells):
                    out.append("| " + " | ".join(cells) + " |")
        elif tag == "glossary":
            _read_glossary(child, glossary)
        elif tag in ("note", "quote", "content"):
            _walk(child, depth, out, terms, glossary)


def convert_module(xml: bytes) -> dict:
    root = fromstring(xml)
    title_element = root.find(f"{CNX}title")
    title = _clean(_inline(title_element, [])) if title_element is not None else ""
    out: list[str] = [f"# {title}"] if title else []
    terms: list[str] = []
    glossary: list[dict] = []
    content = root.find(f"{CNX}content")
    if content is not None:
        _walk(content, 1, out, terms, glossary)
    glossary_root = root.find(f"{CNX}glossary")
    if glossary_root is not None:
        _read_glossary(glossary_root, glossary)
    return {
        "title": title,
        "markup": "\n\n".join(out) + "\n",
        "terms": list(dict.fromkeys(terms)),
        "glossary": glossary,
    }
