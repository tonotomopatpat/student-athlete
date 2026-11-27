"""Training loop: mixed precision, gradient accumulation, live progress, samples, checkpoints and exact resume.

A run lives in runs/<name>/: config.json, git_commit.txt, metrics.csv, samples.md, state.json, tb/ (TensorBoard),
checkpoints/step-*.pt (last few) and best.pt (lowest validation loss).
"""

import csv
import json
import math
import shutil
import signal
import subprocess
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import torch
from torch.utils.tensorboard import SummaryWriter

from app.core.config import BACKEND_DIR
from app.lm.config import RunConfig, TrainConfig, config_from_dict
from app.lm.data import PretrainStream
from app.lm.model import Seq2SeqTransformer
from app.lm.tokenizer import Tokenizer

CHECKPOINTS = "checkpoints"
BEST = "best.pt"
METRIC_FIELDS = ("step", "windows", "tokens", "loss", "val_loss", "lr", "grad_norm", "tokens_per_second",
                 "elapsed_seconds")


class TrainingDiverged(RuntimeError):
    pass


@dataclass
class TrainState:
    step: int = 0
    windows: int = 0
    best_val_loss: float | None = None
    elapsed_seconds: float = 0.0
    lr_scale: float = 1.0


def pick_device(prefer: str = "auto") -> torch.device:
    if prefer != "auto":
        return torch.device(prefer)
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def autocast_dtype(device: torch.device, precision: str) -> torch.dtype | None:
    if precision == "fp32" or device.type != "cuda":
        return None
    if torch.cuda.is_bf16_supported():
        return torch.bfloat16
    if precision == "bf16":
        raise RuntimeError("This GPU does not support bfloat16. Set precision to fp32 in the config.")
    return None


def learning_rate(step: int, total_steps: int, train: TrainConfig) -> float:
    """Linear warm-up, then cosine decay to min_lr_ratio of the peak."""
    if step < train.warmup_steps:
        return train.learning_rate * (step + 1) / train.warmup_steps
    progress = min(1.0, (step - train.warmup_steps) / max(1, total_steps - train.warmup_steps))
    cosine = 0.5 * (1.0 + math.cos(math.pi * progress))
    return train.learning_rate * (train.min_lr_ratio + (1.0 - train.min_lr_ratio) * cosine)


def build_optimizer(model: Seq2SeqTransformer, train: TrainConfig, device: torch.device) -> torch.optim.AdamW:
    decay, no_decay = [], []
    for name, parameter in model.named_parameters():
        (decay if parameter.dim() >= 2 and not name.startswith("embedding") else no_decay).append(parameter)
    return torch.optim.AdamW(
        [{"params": decay, "weight_decay": train.weight_decay}, {"params": no_decay, "weight_decay": 0.0}],
        lr=train.learning_rate, betas=(0.9, 0.95), eps=1e-8, fused=device.type == "cuda",
    )


def format_duration(seconds: float) -> str:
    seconds = int(max(0, seconds))
    days, rest = divmod(seconds, 86_400)
    hours, rest = divmod(rest, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{days}d {hours:02d}:{minutes:02d}:{secs:02d}" if days else f"{hours:02d}:{minutes:02d}:{secs:02d}"


def git_commit() -> str:
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=BACKEND_DIR, capture_output=True, text=True,
                              timeout=10, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=BACKEND_DIR, capture_output=True, text=True,
                               timeout=10, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return f"{head}{' (uncommitted changes)' if dirty else ''}"


class GpuTemperature:
    """Reads the GPU temperature through nvidia-smi at most every 30 seconds; None when unavailable."""

    def __init__(self) -> None:
        self.command = shutil.which("nvidia-smi")
        self.last_read, self.value = 0.0, None

    def read(self) -> int | None:
        if self.command and time.monotonic() - self.last_read > 30:
            self.last_read = time.monotonic()
            try:
                out = subprocess.run([self.command, "--query-gpu=temperature.gpu", "--format=csv,noheader"],
                                     capture_output=True, text=True, timeout=5, check=True).stdout
                self.value = int(out.split()[0])
            except (OSError, subprocess.SubprocessError, ValueError, IndexError):
                self.command = None
        return self.value


class StopFlag:
    """First Ctrl+C: finish the step, save a checkpoint and exit. Second Ctrl+C: quit immediately."""

    def __init__(self, out: Callable[[str], None]) -> None:
        self.requested = False
        self.out = out
        self.previous = signal.signal(signal.SIGINT, self._handle)

    def _handle(self, signum: int, frame: object) -> None:
        if self.requested:
            signal.signal(signal.SIGINT, self.previous)
            raise KeyboardInterrupt
        self.requested = True
        self.out("\nStopping after this step and saving a checkpoint. Press Ctrl+C again to quit without saving.")

    def close(self) -> None:
        signal.signal(signal.SIGINT, self.previous)


def memory_gb(device: torch.device) -> float:
    if device.type == "cuda":
        return torch.cuda.max_memory_allocated(device) / 1e9
    if device.type == "mps":
        return torch.mps.current_allocated_memory() / 1e9
    return 0.0


def latest_checkpoint(run_dir: Path) -> Path | None:
    checkpoints = sorted((run_dir / CHECKPOINTS).glob("step-*.pt"))
    return checkpoints[-1] if checkpoints else None


def load_weights(model: Seq2SeqTransformer, path: Path) -> None:
    payload = torch.load(path, map_location="cpu", weights_only=False)
    model.load_state_dict(payload["model"])


class Trainer:
    def __init__(self, run_dir: Path, config: RunConfig, train_stream: PretrainStream,
                 val_stream: PretrainStream | None = None, tokenizer: Tokenizer | None = None,
                 samples: Sequence[tuple[np.ndarray, np.ndarray]] = (), device: torch.device | None = None,
                 out: Callable[[str], None] = print) -> None:
        self.run_dir, self.config, self.train, self.out = run_dir, config, config.train, out
        self.train_stream, self.val_stream, self.tokenizer, self.samples = train_stream, val_stream, tokenizer, samples
        self.device = device or pick_device()
        torch.manual_seed(self.train.seed)
        self.model = Seq2SeqTransformer(config.model).to(self.device)
        self.model.gradient_checkpointing = self.train.gradient_checkpointing
        self.optimizer = build_optimizer(self.model, self.train, self.device)
        self.autocast = autocast_dtype(self.device, self.train.precision)
        self.state = TrainState()
        self.windows_per_step = self.train.micro_batch_size * self.train.grad_accum_steps
        self.total_steps = len(train_stream) // self.windows_per_step
        if self.total_steps == 0:
            raise ValueError("Not enough training data for one optimizer step.")
        self.window_tokens = train_stream.settings.lengths[0]
        self.temperature = GpuTemperature()

    # -- run directory ----------------------------------------------------------------------------------------

    def start_new(self, init_weights: Path | None = None) -> None:
        if (self.run_dir / CHECKPOINTS).exists():
            raise FileExistsError(f"{self.run_dir} already has checkpoints. Use --resume, or choose a new --run name.")
        (self.run_dir / CHECKPOINTS).mkdir(parents=True, exist_ok=True)
        (self.run_dir / "config.json").write_text(json.dumps(self.config.to_dict(), indent=2))
        (self.run_dir / "git_commit.txt").write_text(git_commit() + "\n")
        with (self.run_dir / "metrics.csv").open("w", newline="") as handle:
            csv.writer(handle).writerow(METRIC_FIELDS)
        if init_weights is not None:
            load_weights(self.model, init_weights)
            self.out(f"Started from weights in {init_weights}")

    def resume(self, lr_scale: float | None = None) -> None:
        saved = config_from_dict(json.loads((self.run_dir / "config.json").read_text()))
        if saved != self.config:
            raise ValueError("The config differs from the one this run started with. Resume with the run's own config.")
        checkpoint_path = latest_checkpoint(self.run_dir)
        if checkpoint_path is None:
            raise FileNotFoundError(f"No checkpoint in {self.run_dir / CHECKPOINTS}")
        payload = torch.load(checkpoint_path, map_location=self.device, weights_only=False)
        self.model.load_state_dict(payload["model"])
        self.optimizer.load_state_dict(payload["optimizer"])
        self.state = TrainState(**payload["state"])
        torch.set_rng_state(payload["torch_rng"])
        if lr_scale is not None:
            self.state.lr_scale = lr_scale
        self.out(f"Resumed {self.run_dir.name} at step {self.state.step:,} of {self.total_steps:,} "
                 f"(learning-rate scale {self.state.lr_scale}).")

    def _checkpoint_bytes(self) -> int:
        return self.model.parameter_count() * 4 * 4

    def save_checkpoint(self) -> Path:
        directory = self.run_dir / CHECKPOINTS
        free = shutil.disk_usage(directory).free
        if free < 2 * self._checkpoint_bytes():
            raise OSError(f"Only {free / 1e9:.1f} GB free; free up disk space before training continues.")
        path = directory / f"step-{self.state.step:08d}.pt"
        temporary = path.with_suffix(".tmp")
        torch.save({"model": self.model.state_dict(), "optimizer": self.optimizer.state_dict(),
                    "state": asdict(self.state), "config": self.config.to_dict(),
                    "torch_rng": torch.get_rng_state()}, temporary)
        temporary.replace(path)
        for old in sorted(directory.glob("step-*.pt"))[:-self.train.keep_checkpoints]:
            old.unlink()
        (self.run_dir / "state.json").write_text(json.dumps(
            {**asdict(self.state), "total_steps": self.total_steps, "checkpoint": path.name}, indent=2))
        return path

    def _save_best(self) -> None:
        temporary = self.run_dir / f"{BEST}.tmp"
        torch.save({"model": self.model.state_dict(), "config": self.config.to_dict(), "state": asdict(self.state)},
                   temporary)
        temporary.replace(self.run_dir / BEST)

    # -- steps --------------------------------------------------------------------------------------------------

    def _tensors(self, batch: tuple[np.ndarray, np.ndarray]) -> tuple[torch.Tensor, torch.Tensor]:
        inputs, targets = batch
        return torch.from_numpy(inputs).to(self.device), torch.from_numpy(targets).to(self.device)

    def _loss(self, inputs: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        with torch.autocast(self.device.type, dtype=self.autocast, enabled=self.autocast is not None):
            return self.model(inputs, targets)[1]

    def train_step(self) -> tuple[float, float]:
        lr = learning_rate(self.state.step, self.total_steps, self.train) * self.state.lr_scale
        for group in self.optimizer.param_groups:
            group["lr"] = lr
        total = torch.zeros((), device=self.device)
        for _ in range(self.train.grad_accum_steps):
            inputs, targets = self._tensors(self.train_stream.batch(self.state.windows))
            self.state.windows += inputs.shape[0]
            loss = self._loss(inputs, targets)
            (loss / self.train.grad_accum_steps).backward()
            total += loss.detach()
        grad_norm = torch.nn.utils.clip_grad_norm_(self.model.parameters(), self.train.max_grad_norm)
        loss_value = total.item() / self.train.grad_accum_steps
        if not math.isfinite(loss_value) or not math.isfinite(grad_norm.item()):
            raise TrainingDiverged(
                f"Loss became {loss_value} at step {self.state.step}. Nothing was saved from this step. "
                f"Resume from the last checkpoint with half the learning rate: "
                f"python -m app.lm pretrain --resume {self.run_dir.name} --lr-scale {self.state.lr_scale / 2}")
        self.optimizer.step()
        self.optimizer.zero_grad(set_to_none=True)
        self.state.step += 1
        return loss_value, grad_norm.item()

    @torch.no_grad()
    def evaluate(self) -> float | None:
        if self.val_stream is None:
            return None
        self.model.eval()
        losses = []
        for batch_index in range(self.train.eval_batches):
            position = batch_index * self.train.micro_batch_size
            if position >= len(self.val_stream):
                break
            losses.append(self._loss(*self._tensors(self.val_stream.batch(position))).item())
        self.model.train()
        return sum(losses) / len(losses) if losses else None

    @torch.no_grad()
    def write_samples(self) -> None:
        if not self.samples or self.tokenizer is None:
            return
        self.model.eval()
        lines = [f"\n## Step {self.state.step:,}\n"]
        for index, (inputs, targets) in enumerate(self.samples, 1):
            source = torch.from_numpy(inputs[None, :]).to(self.device)
            with torch.autocast(self.device.type, dtype=self.autocast, enabled=self.autocast is not None):
                predicted = self.model.generate_greedy(source, max_new_tokens=len(targets) + 8)[0]
            shown = self.tokenizer.decode(inputs)
            lines += [f"**Sample {index}**", "", f"- Text with blanks: {shown[:400]}",
                      f"- Model fills in: {self.tokenizer.decode(predicted.tolist())}",
                      f"- Correct answer: {self.tokenizer.decode(targets)}", ""]
        self.model.train()
        text = "\n".join(lines)
        with (self.run_dir / "samples.md").open("a", encoding="utf-8") as handle:
            handle.write(text + "\n")
        self.out(text)

    # -- loop ---------------------------------------------------------------------------------------------------

    def _log(self, writer: SummaryWriter, row: dict) -> None:
        for key in ("loss", "val_loss", "lr", "grad_norm", "tokens_per_second"):
            if row.get(key) is not None:
                writer.add_scalar(f"train/{key}", row[key], row["step"])
        with (self.run_dir / "metrics.csv").open("a", newline="") as handle:
            csv.writer(handle).writerow([row.get(field, "") for field in METRIC_FIELDS])

    def run(self, max_steps: int | None = None) -> TrainState:
        """Train until the token budget is used, `max_steps` is reached or Ctrl+C. Always ends with a checkpoint."""
        stop_at = self.total_steps if max_steps is None else min(max_steps, self.total_steps)
        self.model.train()
        stop = StopFlag(self.out)
        started = time.monotonic() - self.state.elapsed_seconds
        last_checkpoint = last_log = time.monotonic()
        windows_at_log = self.state.windows
        self.out(f"Training {self.model.parameter_count() / 1e6:.1f}M parameters on {self.device} "
                 f"({'bfloat16' if self.autocast else 'float32'}), {self.total_steps:,} steps. "
                 f"Ctrl+C saves and stops.")
        try:
            with SummaryWriter(str(self.run_dir / "tb")) as writer:
                while self.state.step < stop_at and not stop.requested:
                    loss, grad_norm = self.train_step()
                    self.state.elapsed_seconds = time.monotonic() - started
                    step = self.state.step
                    if step % self.train.log_every == 0 or step == stop_at:
                        now = time.monotonic()
                        speed = (self.state.windows - windows_at_log) * self.window_tokens / max(now - last_log, 1e-9)
                        last_log, windows_at_log = now, self.state.windows
                        remaining = (self.total_steps - step) * self.windows_per_step * self.window_tokens / max(speed, 1e-9)
                        temperature = self.temperature.read()
                        lr = self.optimizer.param_groups[0]["lr"]
                        self.out(f"step {step:,}/{self.total_steps:,} | loss {loss:.4f} | lr {lr:.2e} | "
                                 f"{speed:,.0f} tok/s | elapsed {format_duration(self.state.elapsed_seconds)} | "
                                 f"left {format_duration(remaining)} | mem {memory_gb(self.device):.2f} GB"
                                 + (f" | GPU {temperature}°C" if temperature is not None else ""))
                        self._log(writer, {"step": step, "windows": self.state.windows,
                                           "tokens": self.state.windows * self.window_tokens, "loss": loss, "lr": lr,
                                           "grad_norm": grad_norm, "tokens_per_second": speed,
                                           "elapsed_seconds": round(self.state.elapsed_seconds, 1)})
                    if step % self.train.eval_every == 0 or step == self.total_steps:
                        self._evaluate_and_log(writer)
                    if step % self.train.sample_every == 0:
                        self.write_samples()
                    if time.monotonic() - last_checkpoint >= self.train.checkpoint_minutes * 60:
                        self.out(f"Checkpoint saved: {self.save_checkpoint().name}")
                        last_checkpoint = time.monotonic()
                path = self.save_checkpoint()
                self.out(f"Checkpoint saved: {path.name}. "
                         + ("Training finished." if self.state.step >= self.total_steps
                            else f"Resume with: python -m app.lm pretrain --resume {self.run_dir.name}"))
        finally:
            stop.close()
        return self.state

    def _evaluate_and_log(self, writer: SummaryWriter) -> None:
        val_loss = self.evaluate()
        if val_loss is None:
            return
        improved = self.state.best_val_loss is None or val_loss < self.state.best_val_loss
        if improved:
            self.state.best_val_loss = val_loss
            self._save_best()
        self.out(f"validation loss {val_loss:.4f}" + (" (best so far, saved best.pt)" if improved else ""))
        self._log(writer, {"step": self.state.step, "windows": self.state.windows,
                           "tokens": self.state.windows * self.window_tokens, "val_loss": val_loss,
                           "elapsed_seconds": round(self.state.elapsed_seconds, 1)})
