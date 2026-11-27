"""Span corruption, the pretraining objective of T5 (Raffel et al. 2020).

About 15% of a token window is removed in short spans. Each span is replaced by a sentinel token in the input,
and the target lists each sentinel followed by the tokens it hides. The model learns to fill in the blanks.
"""

from collections.abc import Sequence

import numpy as np


def window_lengths(input_length: int, noise_density: float, mean_span_length: float) -> tuple[int, int]:
    """Raw window length that corrupts to exactly `input_length` tokens, and the resulting target length."""

    def corrupted(raw_length: int) -> tuple[int, int]:
        noise = int(round(raw_length * noise_density))
        spans = int(round(noise / mean_span_length))
        return raw_length - noise + spans + 1, noise + spans + 1

    raw = input_length - 1
    while corrupted(raw + 1)[0] <= input_length:
        raw += 1
    return raw, corrupted(raw)[1]


def _segment(num_items: int, num_segments: int, rng: np.random.Generator) -> np.ndarray:
    """Random split of `num_items` into `num_segments` parts, each at least 1."""
    first = np.arange(num_items - 1) < (num_segments - 1)
    rng.shuffle(first)
    segment_id = np.cumsum(np.concatenate([[False], first]))
    return np.bincount(segment_id, minlength=num_segments)


def noise_mask(length: int, noise_density: float, mean_span_length: float, rng: np.random.Generator) -> np.ndarray:
    """Boolean mask of noise positions. Spans alternate keep, noise, keep, noise and the window starts with keep."""
    if length < 2:
        raise ValueError("window must have at least 2 tokens")
    noise = min(max(int(round(length * noise_density)), 1), length - 1)
    spans = max(min(int(round(noise / mean_span_length)), noise, length - noise), 1)
    noise_lengths = _segment(noise, spans, rng)
    keep_lengths = _segment(length - noise, spans, rng)
    interleaved = np.stack([keep_lengths, noise_lengths], axis=1).reshape(-1)
    starts = np.cumsum(interleaved)[:-1]
    indicator = np.zeros(length, dtype=np.int64)
    indicator[starts] = 1
    return np.cumsum(indicator) % 2 == 1


def _replace_spans(tokens: np.ndarray, mask: np.ndarray, sentinels: np.ndarray) -> np.ndarray:
    previous = np.concatenate([[False], mask[:-1]])
    first = mask & ~previous
    index = np.cumsum(first) - 1
    if first.any() and index.max() >= len(sentinels):
        raise ValueError("not enough sentinel tokens for this many spans")
    out = np.where(first, sentinels[np.clip(index, 0, None)], tokens)
    return out[~(mask & ~first)]


def corrupt(tokens: np.ndarray, sentinels: Sequence[int], eos_id: int, noise_density: float,
            mean_span_length: float, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """Return (input ids, target ids), both ending with EOS."""
    tokens = np.asarray(tokens, dtype=np.int64)
    sentinel_ids = np.asarray(sentinels, dtype=np.int64)
    mask = noise_mask(len(tokens), noise_density, mean_span_length, rng)
    inputs = np.append(_replace_spans(tokens, mask, sentinel_ids), eos_id)
    targets = np.append(_replace_spans(tokens, ~mask, sentinel_ids), eos_id)
    return inputs, targets
