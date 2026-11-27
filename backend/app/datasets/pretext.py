"""Pretraining text: plain English paragraphs from the corpus, exact duplicates removed, gold lessons kept out.

Output: data/corpus/clean/<source>.txt with one paragraph per line and a blank line after each document, plus
report.json. Sources are the id prefixes of corpus documents (openstax, wiki-en, wiki-simple, ...).
"""

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from app.datasets import corpus
from app.datasets.sources import CORPUS_DIR
from app.nlp.language import detect_language

CLEAN_DIR = CORPUS_DIR / "clean"
REPORT_FILE = "report.json"
MIN_DOCUMENT_WORDS = 50
MIN_DEDUPE_WORDS = 8
SKIP_TITLES = re.compile(r"^(preface|index|answer key|references|glossary|appendix\b.*)$", re.IGNORECASE)
HEADING = re.compile(r"^#+\s*")
BULLET = re.compile(r"^[-*\u2022]\s+")


def source_of(document_id: str) -> str:
    return document_id.split(":", 1)[0]


def plain_paragraphs(markup: str) -> list[str]:
    """Our lesson markup to plain lines: headings and list items keep their text, tables and bold marks go."""
    out = []
    for line in markup.splitlines():
        line = line.strip()
        if not line or line.startswith("|"):
            continue
        line = BULLET.sub("", HEADING.sub("", line)).replace("**", "")
        line = " ".join(line.split())
        if line:
            out.append(line)
    return out


def _fingerprint(paragraph: str) -> int:
    normalized = " ".join(re.findall(r"\w+", paragraph.lower()))
    return int.from_bytes(hashlib.blake2b(normalized.encode(), digest_size=8).digest(), "big")


def build_clean_corpus(out_dir: Path = CLEAN_DIR, root: Path = CORPUS_DIR, progress=print) -> dict:  # noqa: ANN001
    """One pass over every corpus document. Returns and saves a report with counts per source."""
    gold_texts = corpus.gold_lesson_texts()
    gold_set = corpus.gold_shingles(gold_texts)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.txt"):
        old.unlink()
    stats: dict[str, Counter] = {}
    handles = {}
    seen: set[int] = set()
    try:
        for count, document in enumerate(corpus.raw_documents(root), 1):
            source = source_of(document["id"])
            counter = stats.setdefault(source, Counter())
            counter["documents_in"] += 1
            if gold_set:
                drop, hits = corpus.overlapping_parts(document, gold_set)
                if drop:
                    counter["dropped_gold_overlap"] += 1
                    continue
                if hits:
                    dropped = set(hits)
                    parts = document["markup"].split("\n\n")
                    document = {**document, "markup": "\n\n".join(p for i, p in enumerate(parts) if i not in dropped)}
                    counter["paragraphs_dropped_gold_overlap"] += len(hits)
            if SKIP_TITLES.match((document.get("title") or "").strip()):
                counter["dropped_front_or_back_matter"] += 1
                continue
            kept = []
            for paragraph in plain_paragraphs(document["markup"]):
                if len(paragraph.split()) >= MIN_DEDUPE_WORDS:
                    fingerprint = _fingerprint(paragraph)
                    if fingerprint in seen:
                        counter["paragraphs_duplicate"] += 1
                        continue
                    seen.add(fingerprint)
                kept.append(paragraph)
            text = "\n".join(kept)
            words = len(text.split())
            if words < MIN_DOCUMENT_WORDS:
                counter["dropped_too_short"] += 1
                continue
            if detect_language(text) != "en":
                counter["dropped_not_english"] += 1
                continue
            if source not in handles:
                handles[source] = (out_dir / f"{source}.txt").open("w", encoding="utf-8")
            handles[source].write(text + "\n\n")
            counter["documents_kept"] += 1
            counter["paragraphs_kept"] += len(kept)
            counter["words_kept"] += words
            if count % 100_000 == 0:
                progress(f"{count:,} documents read")
    finally:
        for handle in handles.values():
            handle.close()
    report = {
        "gold_lessons": len(gold_texts),
        "sources": {source: dict(counter) for source, counter in sorted(stats.items())},
        "words_kept": sum(counter["words_kept"] for counter in stats.values()),
    }
    (out_dir / REPORT_FILE).write_text(json.dumps(report, indent=2))
    return report


def iter_documents(path: Path):  # noqa: ANN201
    """Documents of one clean file as lists of paragraphs."""
    paragraphs: list[str] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.rstrip("\n")
            if line:
                paragraphs.append(line)
            elif paragraphs:
                yield paragraphs
                paragraphs = []
    if paragraphs:
        yield paragraphs
