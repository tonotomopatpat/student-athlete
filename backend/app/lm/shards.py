"""From clean text to model input: the tokenizer's training sample and the uint16 token shards.

About 0.5% of documents (chosen by a hash of their text, so the choice never changes) go to the validation shard.
OpenStax is repeated `repeats["openstax"]` times in training because it reads most like the lessons.
"""

import hashlib
import json
import random
from collections import Counter
from pathlib import Path

import numpy as np

from app.datasets.pretext import iter_documents
from app.lm.data import META_FILE, TOKEN_DTYPE
from app.lm.tokenizer import Tokenizer

DEFAULT_REPEATS = {"openstax": 3}
VAL_PER_MILLE = 5
SHARD_TOKENS = 100_000_000
ENCODE_BATCH = 2000


def _clean_files(clean_dir: Path) -> list[Path]:
    files = sorted(clean_dir.glob("*.txt"))
    if not files:
        raise FileNotFoundError(f"No clean text in {clean_dir}. Run: python -m app.lm corpus-build")
    return files


def write_tokenizer_sample(clean_dir: Path, out_file: Path, max_lines: int, repeats: dict[str, int] | None = None,
                           seed: int = 7) -> dict[str, int]:
    """A random sample of paragraphs, each source weighted by its size times its repeat count."""
    repeats = DEFAULT_REPEATS if repeats is None else repeats
    files = _clean_files(clean_dir)
    lines = {}
    for path in files:
        with path.open(encoding="utf-8") as handle:
            lines[path.stem] = sum(1 for line in handle if line.strip())
    weights = {source: count * repeats.get(source, 1) for source, count in lines.items()}
    total_weight = sum(weights.values()) or 1
    rng = random.Random(seed)
    written: Counter = Counter()
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with out_file.open("w", encoding="utf-8") as out:
        for path in files:
            source = path.stem
            keep = min(1.0, max_lines * weights[source] / total_weight / max(lines[source], 1))
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    if line.strip() and rng.random() < keep:
                        out.write(line)
                        written[source] += 1
    return dict(written)


def _is_validation(paragraphs: list[str]) -> bool:
    digest = hashlib.blake2b("\n".join(paragraphs).encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big") % 1000 < VAL_PER_MILLE


class ShardWriter:
    def __init__(self, out_dir: Path, split: str, shard_tokens: int) -> None:
        self.out_dir, self.split, self.shard_tokens = out_dir, split, shard_tokens
        self.buffer: list[np.ndarray] = []
        self.buffered = 0
        self.files: list[str] = []
        self.tokens = 0

    def add(self, ids: np.ndarray) -> None:
        self.buffer.append(ids)
        self.buffered += len(ids)
        self.tokens += len(ids)
        if self.buffered >= self.shard_tokens:
            self.flush()

    def flush(self) -> None:
        if not self.buffered:
            return
        path = self.out_dir / f"{self.split}-{len(self.files):05d}.bin"
        np.concatenate(self.buffer).astype(TOKEN_DTYPE).tofile(path)
        self.files.append(path.name)
        self.buffer, self.buffered = [], 0


def build_shards(clean_dir: Path, tokenizer: Tokenizer, out_dir: Path, repeats: dict[str, int] | None = None,
                 shard_tokens: int = SHARD_TOKENS, progress=print) -> dict:  # noqa: ANN001
    repeats = DEFAULT_REPEATS if repeats is None else repeats
    if tokenizer.vocab_size > np.iinfo(TOKEN_DTYPE).max + 1:
        raise ValueError("vocabulary too large for uint16 shards")
    if any(out_dir.glob("*.bin")):
        raise FileExistsError(f"{out_dir} already has shards. Delete the folder or choose another --out.")
    out_dir.mkdir(parents=True, exist_ok=True)
    train, val = ShardWriter(out_dir, "train", shard_tokens), ShardWriter(out_dir, "val", shard_tokens)
    sources: dict[str, Counter] = {}

    def encode(batch: list[list[str]], source: str) -> None:
        counter = sources[source]
        encoded = tokenizer.encode_batch([" ".join(paragraphs) for paragraphs in batch])
        for paragraphs, ids in zip(batch, encoded):
            array = np.asarray([*ids, tokenizer.eos_id], dtype=TOKEN_DTYPE)
            if _is_validation(paragraphs):
                val.add(array)
                counter["val_tokens"] += len(array)
            else:
                for _ in range(repeats.get(source, 1)):
                    train.add(array)
                counter["train_tokens"] += len(array) * repeats.get(source, 1)
            counter["documents"] += 1

    for path in _clean_files(clean_dir):
        source = path.stem
        sources[source] = Counter()
        batch: list[list[str]] = []
        for paragraphs in iter_documents(path):
            batch.append(paragraphs)
            if len(batch) >= ENCODE_BATCH:
                encode(batch, source)
                batch = []
        if batch:
            encode(batch, source)
        progress(f"{source}: {sources[source]['documents']:,} documents, "
                 f"{sources[source]['train_tokens']:,} training tokens")
    train.flush()
    val.flush()
    meta = {
        "tokenizer_sha256": tokenizer.sha256(), "vocab_size": tokenizer.vocab_size, "eos_id": tokenizer.eos_id,
        "repeats": repeats, "train_tokens": train.tokens, "val_tokens": val.tokens,
        "train_files": train.files, "val_files": val.files,
        "sources": {source: dict(counter) for source, counter in sources.items()},
    }
    (out_dir / META_FILE).write_text(json.dumps(meta, indent=2))
    return meta
