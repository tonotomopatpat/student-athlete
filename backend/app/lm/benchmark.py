"""Measures training speed and memory for each model size on this machine, then applies rule G1:
choose the largest size that finishes the token budget within MAX_DAYS; if none does, shrink the budget."""

import json
import time
from datetime import datetime
from pathlib import Path

import torch

from app.lm.config import RunConfig
from app.lm.model import Seq2SeqTransformer
from app.lm.noise import window_lengths
from app.lm.train import autocast_dtype, build_optimizer, memory_gb

MAX_DAYS = 5


def _synchronize(device: torch.device) -> None:
    if device.type == "cuda":
        torch.cuda.synchronize()
    elif device.type == "mps":
        torch.mps.synchronize()


def _is_out_of_memory(error: RuntimeError) -> bool:
    return "out of memory" in str(error).lower()


def _measure(config: RunConfig, device: torch.device, micro_batch: int, checkpointing: bool, steps: int) -> dict:
    train = config.train
    raw_length, target_length = window_lengths(train.input_length, train.noise_density, train.mean_span_length)
    model = Seq2SeqTransformer(config.model).to(device)
    model.gradient_checkpointing = checkpointing
    optimizer = build_optimizer(model, train, device)
    dtype = autocast_dtype(device, train.precision)
    inputs = torch.randint(3, config.model.vocab_size, (micro_batch, train.input_length), device=device)
    targets = torch.randint(3, config.model.vocab_size, (micro_batch, target_length), device=device)
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)
    try:
        elapsed = 0.0
        for step in range(steps + 2):
            start = time.perf_counter()
            with torch.autocast(device.type, dtype=dtype, enabled=dtype is not None):
                loss = model(inputs, targets)[1]
            loss.backward()
            optimizer.step()
            optimizer.zero_grad(set_to_none=True)
            _synchronize(device)
            if step >= 2:
                elapsed += time.perf_counter() - start
        tokens_per_second = micro_batch * raw_length * steps / elapsed
        return {
            "parameters_millions": round(model.parameter_count() / 1e6, 1),
            "micro_batch_size": micro_batch, "gradient_checkpointing": checkpointing,
            "tokens_per_second": round(tokens_per_second), "peak_memory_gb": round(memory_gb(device), 2),
            "hours_for_budget": round(train.total_tokens / tokens_per_second / 3600, 1),
        }
    finally:
        del model, optimizer
        if device.type == "cuda":
            torch.cuda.empty_cache()


def benchmark(config: RunConfig, device: torch.device, steps: int = 8) -> dict:
    """Try the configured micro-batch, then smaller ones and gradient checkpointing until it fits in memory."""
    micro_batch = config.train.micro_batch_size
    attempts = []
    while micro_batch >= 1:
        for checkpointing in (config.train.gradient_checkpointing, True):
            try:
                return {**_measure(config, device, micro_batch, checkpointing, steps), "fits": True}
            except RuntimeError as error:
                if not _is_out_of_memory(error):
                    raise
                attempts.append(f"micro-batch {micro_batch}{' with checkpointing' if checkpointing else ''}")
                if device.type == "cuda":
                    torch.cuda.empty_cache()
        micro_batch //= 2
    return {"fits": False, "out_of_memory": attempts}


def recommend(results: dict[str, dict], budget_tokens: int) -> str:
    fitting = {name: result for name, result in results.items() if result.get("fits")}
    if not fitting:
        return "No size fits in memory on this machine. Send the output to the agent."
    in_time = [name for name, result in fitting.items() if result["hours_for_budget"] <= MAX_DAYS * 24]
    if in_time:
        best = max(in_time, key=lambda name: fitting[name]["parameters_millions"])
        result = fitting[best]
        return (f"Use {best}: about {result['hours_for_budget'] / 24:.1f} days for {budget_tokens / 1e9:.1f}B tokens "
                f"with micro-batch {result['micro_batch_size']}"
                f"{' and gradient checkpointing' if result['gradient_checkpointing'] else ''}.")
    fastest = max(fitting, key=lambda name: fitting[name]["tokens_per_second"])
    tokens = int(fitting[fastest]["tokens_per_second"] * MAX_DAYS * 86_400)
    return (f"No size finishes within {MAX_DAYS} days. Use {fastest} with total_tokens reduced to about "
            f"{tokens / 1e9:.2f}B.")


def run(configs: dict[str, RunConfig], device: torch.device, out_path: Path, steps: int = 8, out=print) -> dict:  # noqa: ANN001
    results = {}
    for name, config in configs.items():
        out(f"Measuring {name} ...")
        results[name] = benchmark(config, device, steps)
        out(f"  {json.dumps(results[name])}")
    budget = next(iter(configs.values())).train.total_tokens
    payload = {"device": str(device), "gpu": torch.cuda.get_device_name(0) if device.type == "cuda" else device.type,
               "measured_at": datetime.now().isoformat(timespec="seconds"), "results": results,
               "recommendation": recommend(results, budget)}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2))
    out(f"\nRule G1: {payload['recommendation']}\nSaved to {out_path}")
    return payload
