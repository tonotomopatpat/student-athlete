"""Fetch OpenStax textbooks (CNXML on GitHub) into JSONL: one line per module with markup, key terms and glossary."""

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from defusedxml.ElementTree import fromstring

from app.datasets.cnxml import convert_module
from app.datasets.http import FetchError, fetch
from app.datasets.sources import OPENSTAX_DIR, OPENSTAX_RAW

logger = logging.getLogger(__name__)

COLLXML = "{http://cnx.rice.edu/collxml}"
MDML = "{http://cnx.rice.edu/mdml}"
WORKERS = 12


def _raw(repo: str, path: str) -> bytes:
    return fetch(OPENSTAX_RAW.format(repo=repo, path=path))


def _book_collections(repo: str) -> list[tuple[str, str]]:
    books = _raw(repo, "META-INF/books.xml").decode("utf-8")
    return re.findall(r'slug="([^"]+)"[^>]*href="\.\./([^"]+)"', books)


def _modules(collection: bytes) -> tuple[dict, list[tuple[str, str]]]:
    """Book metadata and (module id, chapter title) in reading order."""
    root = fromstring(collection)
    license_element = root.find(f".//{MDML}license")
    title_element = root.find(f".//{MDML}title")
    info = {
        "title": title_element.text if title_element is not None else "",
        "license": (license_element.text or "").strip() if license_element is not None else "",
        "license_url": license_element.get("url", "") if license_element is not None else "",
    }
    order: list[tuple[str, str]] = []

    def walk(element, chapter: str) -> None:  # noqa: ANN001
        for child in element:
            if child.tag == f"{COLLXML}module":
                order.append((child.get("document", ""), chapter))
            elif child.tag == f"{COLLXML}subcollection":
                title = child.find(f"{MDML}title")
                content = child.find(f"{COLLXML}content")
                walk(child if content is None else content, title.text if title is not None and not chapter else chapter)
            elif child.tag == f"{COLLXML}content":
                walk(child, chapter)

    walk(root, "")
    return info, [(module, chapter) for module, chapter in order if module]


def fetch_repo(repo: str, out_dir: Path = OPENSTAX_DIR) -> list[dict]:
    """Download every book in one repository. Returns a summary per book."""
    out_dir.mkdir(parents=True, exist_ok=True)
    summaries = []
    for slug, collection_path in _book_collections(repo):
        target = out_dir / f"{slug}.jsonl"
        info, modules = _modules(_raw(repo, collection_path))

        def load(item: tuple[str, str]) -> dict | None:
            module_id, chapter = item
            try:
                record = convert_module(_raw(repo, f"modules/{module_id}/index.cnxml"))
            except FetchError as error:
                logger.warning("Skipping %s: %s", module_id, error)
                return None
            return {"id": f"openstax:{slug}:{module_id}", "book": slug, "chapter": chapter, **record}

        with ThreadPoolExecutor(WORKERS) as pool:
            records = [record for record in pool.map(load, modules) if record]
        with target.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        words = sum(len(record["markup"].split()) for record in records)
        summaries.append({
            "source": "openstax", "repo": repo, "book": slug, "title": info["title"], "license": info["license"],
            "license_url": info["license_url"], "modules": len(records), "words": words,
            "url": f"https://github.com/openstax/{repo}",
        })
        logger.info("OpenStax %s: %s modules, %s words", slug, len(records), words)
    return summaries
