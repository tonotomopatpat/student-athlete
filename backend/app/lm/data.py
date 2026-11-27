"""Token shards on disk and the pretraining batch stream.

Shards are flat uint16 arrays (`train-00000.bin`, ..., `val-00000.bin`) with documents separated by EOS, described
by `meta.json`. Training reads fixed windows in a shuffled order that depends only on the seed, so a resumed run
continues with exactly the batches it would have seen.
"""

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.lm.noise import corrupt, window_lengths

META_FILE = "meta.json"
TOKEN_DTYPE = np.uint16


def read_meta(shards_dir: Path) -> dict:
    path = shards_dir / META_FILE
    if not path.is_file():
        raise FileNotFoundError(f"No shards at {shards_dir}. Run: python -m app.lm corpus-shards")
    return json.loads(path.read_text())


def shard_paths(shards_dir: Path, split: str) -> list[Path]:
    paths = sorted(shards_dir.glob(f"{split}-*.bin"))
    if not paths:
        raise FileNotFoundError(f"No {split} shards in {shards_dir}")
    return paths


class WindowIndex:
    """All non-overlapping windows of `window` tokens across a list of shards."""

    def __init__(self, paths: list[Path], window: int) -> None:
        self.arrays = [np.memmap(path, dtype=TOKEN_DTYPE, mode="r") for path in paths]
        self.window = window
        counts = np.array([len(array) // window for array in self.arrays], dtype=np.int64)
        self.offsets = np.concatenate([[0], np.cumsum(counts)])

    def __len__(self) -> int:
        return int(self.offsets[-1])

    def __getitem__(self, index: int) -> np.ndarray:
        shard = int(np.searchsorted(self.offsets, index, side="right") - 1)
        start = (index - int(self.offsets[shard])) * self.window
        return np.asarray(self.arrays[shard][start:start + self.window], dtype=np.int64)


@dataclass(frozen=True)
class SpanSettings:
    input_length: int
    noise_density: float
    mean_span_length: float
    sentinel_ids: tuple[int, ...]
    eos_id: int

    @property
    def lengths(self) -> tuple[int, int]:
        return window_lengths(self.input_length, self.noise_density, self.mean_span_length)


def corrupt_window(tokens: np.ndarray, settings: SpanSettings, seed: int, index: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng([seed, index])
    return corrupt(tokens, settings.sentinel_ids, settings.eos_id, settings.noise_density,
                   settings.mean_span_length, rng)


def _stack(rows: list[np.ndarray], length: int, fill: int) -> np.ndarray:
    out = np.full((len(rows), length), fill, dtype=np.int64)
    for row_index, row in enumerate(rows):
        out[row_index, :len(row)] = row[:length]
    return out


class PretrainStream:
    """Micro-batches of (input ids, target ids) as int64 numpy arrays; target padding is -100."""

    def __init__(self, windows: WindowIndex, settings: SpanSettings, micro_batch_size: int, seed: int,
                 pad_id: int, max_windows: int | None = None) -> None:
        self.windows, self.settings, self.micro_batch_size, self.seed, self.pad_id = (
            windows, settings, micro_batch_size, seed, pad_id)
        total = len(windows) if max_windows is None else min(max_windows, len(windows))
        self.order = np.random.default_rng(seed).permutation(len(windows))[:total]
        self.target_length = settings.lengths[1]

    def __len__(self) -> int:
        return len(self.order)

    def batch(self, position: int) -> tuple[np.ndarray, np.ndarray]:
        """The micro-batch that starts at window `position` of the shuffled order."""
        indices = self.order[position:position + self.micro_batch_size]
        if len(indices) == 0:
            raise IndexError("stream exhausted")
        pairs = [corrupt_window(self.windows[int(index)], self.settings, self.seed, int(index)) for index in indices]
        inputs = _stack([inputs for inputs, _ in pairs], self.settings.input_length, self.pad_id)
        targets = _stack([targets for _, targets in pairs], self.target_length, -100)
        return inputs, targets


def open_stream(shards_dir: Path, split: str, settings: SpanSettings, micro_batch_size: int, seed: int,
                pad_id: int, max_windows: int | None = None) -> PretrainStream:
    windows = WindowIndex(shard_paths(shards_dir, split), settings.lengths[0])
    if len(windows) == 0:
        raise ValueError(f"{split} shards are shorter than one window")
    return PretrainStream(windows, settings, micro_batch_size, seed, pad_id, max_windows)
