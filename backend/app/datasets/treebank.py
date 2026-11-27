"""Universal Dependencies treebanks: download and read CoNLL-U as (words, universal POS tags) sentences."""

from collections.abc import Iterator
from pathlib import Path

from app.datasets.http import fetch
from app.datasets.sources import TREEBANK_DIR, UD_RAW, UD_SPLITS, UD_TREEBANKS

Sentence = tuple[list[str], list[str]]


def treebank_path(name: str, split: str, root: Path = TREEBANK_DIR) -> Path:
    return root / f"{name}-ud-{split}.conllu"


def fetch_treebanks(root: Path = TREEBANK_DIR) -> list[dict]:
    root.mkdir(parents=True, exist_ok=True)
    summaries = []
    for name, info in UD_TREEBANKS.items():
        counts = {}
        for split in UD_SPLITS:
            data = fetch(UD_RAW.format(repo=info["repo"], name=name, split=split))
            treebank_path(name, split, root).write_bytes(data)
            counts[split] = sum(len(words) for words, _ in read_conllu(treebank_path(name, split, root)))
        summaries.append({"source": "universal_dependencies", "treebank": name, "license": info["license"],
                          "citation": info["citation"], "url": f"https://github.com/UniversalDependencies/{info['repo']}",
                          "words": counts})
    return summaries


def read_conllu(path: Path) -> Iterator[Sentence]:
    """Sentences of surface words with UPOS tags. Multiword-token ranges and empty nodes are skipped;
    redacted tokens ("_", as in GUM's Reddit portion) drop the whole sentence."""
    words: list[str] = []
    tags: list[str] = []
    redacted = False
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.rstrip("\n")
            if not line:
                if words and not redacted:
                    yield words, tags
                words, tags, redacted = [], [], False
                continue
            if line.startswith("#"):
                continue
            columns = line.split("\t")
            if len(columns) < 4 or "-" in columns[0] or "." in columns[0]:
                continue
            if columns[1] == "_" and columns[3] != "PUNCT":
                redacted = True
            words.append(columns[1])
            tags.append(columns[3])
    if words and not redacted:
        yield words, tags
