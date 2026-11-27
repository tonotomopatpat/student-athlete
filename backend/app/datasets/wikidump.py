"""Bulk Wikipedia text for pretraining: the `wikimedia/wikipedia` dump, downloaded as Parquet text files.

These are data files only (article text), not a model. Each Parquet shard is converted to our corpus JSONL format
(one article per line) and then deleted to save disk unless keep_parquet is set.
"""

import json
import logging
import re
from pathlib import Path

import pyarrow.parquet as pq

from app.datasets.http import download, fetch
from app.datasets.sources import CORPUS_DIR

logger = logging.getLogger(__name__)

DATASET = "wikimedia/wikipedia"
TREE_API = "https://huggingface.co/api/datasets/wikimedia/wikipedia/tree/main/{config}"
FILE_URL = "https://huggingface.co/datasets/wikimedia/wikipedia/resolve/main/{path}"
LICENSE = "CC BY-SA 3.0 and GFDL (Wikipedia contributors)"
WIKIDUMP_DIR = CORPUS_DIR / "wikidump"
CONFIGS = {"en": "20231101.en", "simple": "20231101.simple"}
END_SECTIONS = re.compile(
    r"^(see also|references|notes|footnotes|further reading|external links|bibliography|sources|citations|"
    r"notes and references|works cited)$", re.IGNORECASE)


def list_shards(config: str) -> list[dict]:
    """Parquet files of one dump config, in order, with their sizes."""
    items = json.loads(fetch(TREE_API.format(config=config)))
    files = [item for item in items if item.get("type") == "file" and item.get("path", "").endswith(".parquet")]
    if not files:
        raise ValueError(f"No Parquet files listed for {config}")
    return sorted(({"path": item["path"], "size": item.get("size")} for item in files), key=lambda item: item["path"])


def article_markup(title: str, text: str) -> str:
    """Article text up to the first reference-style section, with the title as a heading."""
    kept: list[str] = []
    for line in text.splitlines():
        if END_SECTIONS.match(line.strip()):
            break
        kept.append(line)
    paragraphs = [" ".join(part.split()) for part in "\n".join(kept).split("\n\n")]
    return "\n\n".join([f"# {title}", *[part for part in paragraphs if part]]) + "\n"


def convert_shard(parquet_path: Path, out_path: Path, language: str) -> dict:
    articles = words = 0
    temporary = out_path.with_name(out_path.name + ".part")
    with temporary.open("w", encoding="utf-8") as handle:
        for batch in pq.ParquetFile(parquet_path).iter_batches(columns=["id", "title", "text"], batch_size=2000):
            for article_id, title, text in zip(*(column.to_pylist() for column in batch.columns)):
                markup = article_markup(title or "", text or "")
                articles += 1
                words += len(markup.split())
                handle.write(json.dumps({"id": f"wiki-{language}:{article_id}", "title": title, "markup": markup},
                                        ensure_ascii=False) + "\n")
    temporary.replace(out_path)
    return {"articles": articles, "words": words}


def fetch_dump(language: str, shard_limit: int | None, out_dir: Path = WIKIDUMP_DIR,
               keep_parquet: bool = False, progress=print) -> dict:  # noqa: ANN001
    """Download and convert the first `shard_limit` shards (all when None). Already converted shards are skipped."""
    config = CONFIGS[language]
    shards = list_shards(config)
    selected = shards if shard_limit is None else shards[:shard_limit]
    out_dir.mkdir(parents=True, exist_ok=True)
    total_articles = total_words = 0
    for number, shard in enumerate(selected, 1):
        out_path = out_dir / f"{language}-{number - 1:05d}.jsonl"
        done_marker = out_path.with_suffix(".done.json")
        if out_path.is_file() and done_marker.is_file():
            counts = json.loads(done_marker.read_text())
        else:
            parquet_path = out_dir / "parquet" / Path(shard["path"]).name
            progress(f"[{number}/{len(selected)}] downloading {shard['path']} "
                     f"({(shard['size'] or 0) / 1e6:,.0f} MB)")
            download(FILE_URL.format(path=shard["path"]), parquet_path, shard["size"])
            progress(f"[{number}/{len(selected)}] converting to text")
            counts = convert_shard(parquet_path, out_path, language)
            done_marker.write_text(json.dumps(counts))
            if not keep_parquet:
                parquet_path.unlink()
        total_articles += counts["articles"]
        total_words += counts["words"]
        progress(f"[{number}/{len(selected)}] {counts['articles']:,} articles, {counts['words']:,} words")
    return {
        "source": "wikipedia-dump", "selection": f"{config} shards 1-{len(selected)} of {len(shards)}",
        "license": LICENSE, "url": f"https://huggingface.co/datasets/{DATASET}", "articles": total_articles,
        "words": total_words,
    }
