"""Our SentencePiece tokenizer: trained from scratch on our corpus, with control tokens for the model's tasks."""

import hashlib
import json
import os
from collections.abc import Iterable, Sequence
from pathlib import Path

import sentencepiece as spm

PAD, EOS, UNK = "<pad>", "</s>", "<unk>"
HIGHLIGHT, SEPARATOR = "<hl>", "<sep>"
SENTINELS = tuple(f"<extra_id_{index}>" for index in range(100))
MODEL_FILE = "spm.model"
META_FILE = "tokenizer.json"


def train_tokenizer(sample_file: Path, out_dir: Path, vocab_size: int = 32_000, max_sentences: int = 3_000_000,
                    threads: int | None = None, hard_vocab_limit: bool = True) -> dict:
    """Train a unigram model. Control tokens can never come out of encoding plain text, only from our code."""
    out_dir.mkdir(parents=True, exist_ok=True)
    spm.SentencePieceTrainer.train(
        input=str(sample_file),
        model_prefix=str(out_dir / "spm"),
        model_type="unigram",
        vocab_size=vocab_size,
        character_coverage=0.9995,
        byte_fallback=True,
        normalization_rule_name="nmt_nfkc",
        pad_id=0, eos_id=1, unk_id=2, bos_id=-1,
        pad_piece=PAD, eos_piece=EOS, unk_piece=UNK,
        control_symbols=[HIGHLIGHT, SEPARATOR, *SENTINELS],
        input_sentence_size=max_sentences,
        shuffle_input_sentence=True,
        max_sentence_length=16_384,
        num_threads=threads or os.cpu_count() or 4,
        hard_vocab_limit=hard_vocab_limit,
        minloglevel=1,
    )
    tokenizer = Tokenizer(out_dir)
    meta = {
        "vocab_size": tokenizer.vocab_size,
        "sha256": hashlib.sha256((out_dir / MODEL_FILE).read_bytes()).hexdigest(),
        "pad_id": tokenizer.pad_id, "eos_id": tokenizer.eos_id, "unk_id": tokenizer.unk_id,
        "highlight_id": tokenizer.highlight_id, "separator_id": tokenizer.separator_id,
        "sentinel_ids": [tokenizer.sentinel_ids[0], tokenizer.sentinel_ids[-1]],
        "max_sentences": max_sentences,
    }
    (out_dir / META_FILE).write_text(json.dumps(meta, indent=2))
    return meta


class Tokenizer:
    def __init__(self, directory: Path) -> None:
        path = Path(directory) / MODEL_FILE
        if not path.is_file():
            raise FileNotFoundError(f"No tokenizer at {path}. Run: python -m app.lm tokenizer-train")
        self.directory = Path(directory)
        self.sp = spm.SentencePieceProcessor(model_file=str(path))
        self.pad_id, self.eos_id, self.unk_id = self.sp.pad_id(), self.sp.eos_id(), self.sp.unk_id()
        self.highlight_id = self.sp.piece_to_id(HIGHLIGHT)
        self.separator_id = self.sp.piece_to_id(SEPARATOR)
        self.sentinel_ids = [self.sp.piece_to_id(piece) for piece in SENTINELS]
        self._special = {self.highlight_id: HIGHLIGHT, self.separator_id: SEPARATOR,
                         **{token: piece for token, piece in zip(self.sentinel_ids, SENTINELS)}}
        if len({self.pad_id, self.eos_id, self.unk_id, *self._special}) != 3 + len(self._special):
            raise ValueError("tokenizer special tokens are not distinct")

    @property
    def vocab_size(self) -> int:
        return self.sp.get_piece_size()

    def sha256(self) -> str:
        return hashlib.sha256((self.directory / MODEL_FILE).read_bytes()).hexdigest()

    def encode(self, text: str) -> list[int]:
        return self.sp.encode(text)

    def encode_batch(self, texts: Sequence[str], threads: int = -1) -> list[list[int]]:
        return self.sp.encode(list(texts), num_threads=threads)

    def decode(self, ids: Iterable[int]) -> str:
        """Plain text, with control tokens shown as their names and padding and EOS dropped."""
        parts: list[str] = []
        run: list[int] = []
        for token in ids:
            token = int(token)
            if token in (self.pad_id, self.eos_id):
                continue
            if token in self._special:
                if run:
                    parts.append(self.sp.decode(run))
                    run = []
                parts.append(self._special[token])
            else:
                run.append(token)
        if run:
            parts.append(self.sp.decode(run))
        return " ".join(part for part in parts if part)
