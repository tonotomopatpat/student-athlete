"""Model and training settings, loaded from JSON files in backend/configs/."""

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from app.core.config import BACKEND_DIR


@dataclass(frozen=True)
class ModelConfig:
    vocab_size: int = 32_000
    d_model: int = 512
    n_heads: int = 8
    d_ff: int = 2048
    encoder_layers: int = 6
    decoder_layers: int = 6
    dropout: float = 0.0
    max_positions: int = 1024
    pad_id: int = 0
    eos_id: int = 1

    def __post_init__(self) -> None:
        if self.d_model % self.n_heads:
            raise ValueError("d_model must be divisible by n_heads")
        if (self.d_model // self.n_heads) % 2:
            raise ValueError("head size must be even for rotary position embeddings")
        if min(self.vocab_size, self.d_model, self.d_ff, self.encoder_layers, self.decoder_layers) <= 0:
            raise ValueError("model sizes must be positive")
        if not 0.0 <= self.dropout < 1.0:
            raise ValueError("dropout must be in [0, 1)")


@dataclass(frozen=True)
class TrainConfig:
    input_length: int = 512
    noise_density: float = 0.15
    mean_span_length: float = 3.0
    micro_batch_size: int = 8
    grad_accum_steps: int = 8
    learning_rate: float = 1e-3
    min_lr_ratio: float = 0.1
    warmup_steps: int = 2000
    weight_decay: float = 0.01
    max_grad_norm: float = 1.0
    total_tokens: int = 1_200_000_000
    seed: int = 1234
    precision: str = "auto"
    gradient_checkpointing: bool = False
    log_every: int = 20
    eval_every: int = 2000
    eval_batches: int = 50
    sample_every: int = 1000
    checkpoint_minutes: float = 30.0
    keep_checkpoints: int = 3

    def __post_init__(self) -> None:
        if self.precision not in ("auto", "bf16", "fp32"):
            raise ValueError("precision must be auto, bf16 or fp32")
        if not 0.0 < self.noise_density < 0.5:
            raise ValueError("noise_density must be in (0, 0.5)")
        if min(self.micro_batch_size, self.grad_accum_steps, self.total_tokens, self.input_length) <= 0:
            raise ValueError("batch sizes, lengths and token budget must be positive")


@dataclass(frozen=True)
class RunConfig:
    model: ModelConfig
    train: TrainConfig
    tokenizer: str = "models/tokenizer/v1"
    shards: str = "data/corpus/shards"

    @property
    def tokenizer_dir(self) -> Path:
        return resolve(self.tokenizer)

    @property
    def shards_dir(self) -> Path:
        return resolve(self.shards)

    def to_dict(self) -> dict:
        return asdict(self)


def resolve(path: str | Path) -> Path:
    path = Path(path)
    return path if path.is_absolute() else BACKEND_DIR / path


def _build(cls: type, values: dict, where: str):  # noqa: ANN202
    known = {field.name for field in fields(cls)}
    unknown = set(values) - known
    if unknown:
        raise ValueError(f"Unknown {where} settings: {', '.join(sorted(unknown))}")
    return cls(**values)


def config_from_dict(data: dict) -> RunConfig:
    unknown = set(data) - {"model", "train", "tokenizer", "shards"}
    if unknown:
        raise ValueError(f"Unknown config sections: {', '.join(sorted(unknown))}")
    return RunConfig(
        model=_build(ModelConfig, data.get("model", {}), "model"),
        train=_build(TrainConfig, data.get("train", {}), "train"),
        tokenizer=data.get("tokenizer", RunConfig.tokenizer),
        shards=data.get("shards", RunConfig.shards),
    )


def load_config(path: str | Path) -> RunConfig:
    return config_from_dict(json.loads(resolve(path).read_text()))
