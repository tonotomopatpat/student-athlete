"""Checks that a machine is ready to train: GPU, memory, disk, packages and a short speed test."""

import importlib.metadata
import os
import platform
import shutil
import sys
import time

import torch

from app.core.config import BACKEND_DIR

MIN_FREE_DISK_GB = 60
MIN_RAM_GB = 15
PACKAGES = ("numpy", "sentencepiece", "pyarrow", "tensorboard")


def ram_gb() -> float | None:
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1e9
    except (ValueError, OSError, AttributeError):
        return None


def speed_tflops(device: torch.device, dtype: torch.dtype, seconds: float = 5.0) -> float:
    size = 2048 if device.type != "cpu" else 1024
    a = torch.randn(size, size, device=device, dtype=dtype)
    b = torch.randn(size, size, device=device, dtype=dtype)

    def sync() -> None:
        if device.type == "cuda":
            torch.cuda.synchronize()
        elif device.type == "mps":
            torch.mps.synchronize()

    for _ in range(3):
        a @ b
    sync()
    runs, start = 0, time.perf_counter()
    while time.perf_counter() - start < seconds:
        a @ b
        runs += 1
        if runs % 10 == 0:
            sync()
    sync()
    return 2 * size ** 3 * runs / (time.perf_counter() - start) / 1e12


def run_checks() -> tuple[list[tuple[str, str, str]], str]:
    """Rows of (check, value, OK/WARN/FAIL) and the device training would use."""
    rows: list[tuple[str, str, str]] = []
    rows.append(("Python", platform.python_version(), "OK" if sys.version_info >= (3, 11) else "FAIL"))
    rows.append(("PyTorch", torch.__version__, "OK"))
    device = "cpu"
    if torch.cuda.is_available():
        device = "cuda"
        properties = torch.cuda.get_device_properties(0)
        rows.append(("GPU", properties.name, "OK"))
        rows.append(("GPU memory", f"{properties.total_memory / 1e9:.1f} GB", "OK" if properties.total_memory > 3.5e9 else "WARN"))
        rows.append(("CUDA", torch.version.cuda or "?", "OK"))
        rows.append(("bfloat16", "yes" if torch.cuda.is_bf16_supported() else "no",
                     "OK" if torch.cuda.is_bf16_supported() else "WARN"))
    elif torch.backends.mps.is_available():
        device = "mps"
        rows.append(("GPU", "Apple Silicon (MPS)", "OK"))
    else:
        rows.append(("GPU", "none found: training would be very slow", "WARN"))
    memory = ram_gb()
    rows.append(("RAM", f"{memory:.1f} GB" if memory else "unknown",
                 "OK" if memory and memory >= MIN_RAM_GB else "WARN"))
    free = shutil.disk_usage(BACKEND_DIR).free / 1e9
    rows.append(("Free disk", f"{free:.0f} GB (need about {MIN_FREE_DISK_GB})", "OK" if free >= MIN_FREE_DISK_GB else "WARN"))
    for package in PACKAGES:
        try:
            rows.append((package, importlib.metadata.version(package), "OK"))
        except importlib.metadata.PackageNotFoundError:
            rows.append((package, "missing: pip install -r requirements-train.txt", "FAIL"))
    dtype = torch.bfloat16 if device == "cuda" and torch.cuda.is_bf16_supported() else torch.float32
    tflops = speed_tflops(torch.device(device), dtype)
    rows.append(("Speed test", f"{tflops:.1f} TFLOPS ({str(dtype).replace('torch.', '')} on {device})", "OK"))
    return rows, device


def print_report() -> int:
    rows, device = run_checks()
    width = max(len(name) for name, _, _ in rows)
    for name, value, status in rows:
        print(f"[{status:<4}] {name:<{width}}  {value}")
    failures = [name for name, _, status in rows if status == "FAIL"]
    warnings = [name for name, _, status in rows if status == "WARN"]
    if failures:
        print(f"\nNot ready: fix {', '.join(failures)}.")
        return 1
    print(f"\nReady to train on {device}." + (f" Check the warnings: {', '.join(warnings)}." if warnings else ""))
    return 0
