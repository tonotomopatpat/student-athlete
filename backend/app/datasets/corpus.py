"""The background corpus: reading it, and keeping the gold lessons out of it.

A corpus document is dropped when at least DOC_OVERLAP of its word 8-grams also occur in a gold lesson;
otherwise single paragraphs with at least PARAGRAPH_OVERLAP are dropped. This stops the test lessons from
leaking into the statistics and embeddings the generator is built on.
"""

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path

from app.datasets.sources import CORPUS_DIR, CORPUS_MANIFEST, EXCLUSIONS_PATH
from app.evaluation import gold
from app.ingest.extract import extract_document
from app.nlp.tokens import words

NGRAM = 8
DOC_OVERLAP = 0.2
PARAGRAPH_OVERLAP = 0.5


def _shingles(text: str) -> set[int]:
    tokens = words(text)
    return {
        int.from_bytes(hashlib.blake2b(" ".join(tokens[i:i + NGRAM]).encode(), digest_size=8).digest(), "big")
        for i in range(max(0, len(tokens) - NGRAM + 1))
    }


def _overlap(text: str, gold: set[int]) -> float:
    shingles = _shingles(text)
    return len(shingles & gold) / len(shingles) if shingles else 0.0


def corpus_files(root: Path = CORPUS_DIR) -> list[Path]:
    return sorted(path for path in root.glob("*/*.jsonl"))


def raw_documents(root: Path = CORPUS_DIR) -> Iterator[dict]:
    for path in corpus_files(root):
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                yield json.loads(line)


def gold_lesson_texts() -> list[str]:
    """Plain text of every gold lesson listed in the manifest (syllabi are not lessons)."""
    if not gold.MANIFEST_PATH.is_file():
        return []
    texts = []
    for row in gold.read_manifest():
        path = gold.FILES_DIR / row["path"]
        if row["kind"] == "lesson" and path.is_file():
            texts.append(extract_document(path, row["format"]).plain_text())
    return texts


def gold_shingles(gold_texts: list[str]) -> set[int]:
    shingles: set[int] = set()
    for text in gold_texts:
        shingles |= _shingles(text)
    return shingles


def overlapping_parts(document: dict, gold_set: set[int]) -> tuple[bool, list[int]]:
    """(drop the whole document, indexes of paragraphs to drop) for one corpus document."""
    if _overlap(document["markup"], gold_set) >= DOC_OVERLAP:
        return True, []
    return False, [index for index, part in enumerate(document["markup"].split("\n\n"))
                   if len(part.split()) >= NGRAM and _overlap(part, gold_set) >= PARAGRAPH_OVERLAP]


def compute_exclusions(gold_texts: list[str], root: Path = CORPUS_DIR) -> dict:
    gold_set = gold_shingles(gold_texts)
    documents: list[str] = []
    paragraphs: dict[str, list[int]] = {}
    if gold_set:
        for document in raw_documents(root):
            drop, hits = overlapping_parts(document, gold_set)
            if drop:
                documents.append(document["id"])
            elif hits:
                paragraphs[document["id"]] = hits
    return {"gold_documents": len(gold_texts), "documents": documents, "paragraphs": paragraphs}


def update_manifest(entries: list[dict], path: Path = CORPUS_MANIFEST) -> dict:
    """Add or replace source entries (keyed by source and book, treebank or selection) in MANIFEST.json."""
    manifest = json.loads(path.read_text()) if path.is_file() else {"sources": []}

    def key(entry: dict) -> tuple[str, str]:
        return entry["source"], entry.get("book") or entry.get("treebank") or entry.get("selection") or ""

    replaced = {key(entry) for entry in entries}
    manifest["sources"] = [entry for entry in manifest["sources"] if key(entry) not in replaced] + entries
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2))
    return manifest


def save_exclusions(exclusions: dict, path: Path = EXCLUSIONS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(exclusions, indent=1))


def load_exclusions(path: Path = EXCLUSIONS_PATH) -> dict:
    if not path.is_file():
        return {"documents": [], "paragraphs": {}}
    return json.loads(path.read_text())


def documents(root: Path = CORPUS_DIR, exclusions: dict | None = None) -> Iterator[dict]:
    """Corpus documents with gold-overlapping documents and paragraphs removed."""
    exclusions = load_exclusions() if exclusions is None else exclusions
    dropped = set(exclusions.get("documents", []))
    paragraphs = exclusions.get("paragraphs", {})
    for document in raw_documents(root):
        if document["id"] in dropped:
            continue
        if document["id"] in paragraphs:
            skip = set(paragraphs[document["id"]])
            parts = document["markup"].split("\n\n")
            document = {**document, "markup": "\n\n".join(p for i, p in enumerate(parts) if i not in skip)}
        yield document
