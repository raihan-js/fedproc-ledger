"""The environment line recorded in docs/decisions.md (Phase 0: GPU check)."""

from __future__ import annotations

import platform
import sys
from typing import Any


def environment() -> dict[str, Any]:
    info: dict[str, Any] = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "torch": None,
        "cuda_available": None,
        "gpu": None,
        "vram_gb": None,
    }
    try:
        import torch  # optional: installed with the `ml` extra
    except ImportError:
        return info
    info["torch"] = torch.__version__
    info["cuda_available"] = bool(torch.cuda.is_available())
    if info["cuda_available"]:
        props = torch.cuda.get_device_properties(0)
        info["gpu"] = props.name
        info["vram_gb"] = round(props.total_memory / 2**30, 1)
    return info


def gpu_line(info: dict[str, Any]) -> str:
    if info["torch"] is None:
        return "torch not installed (install the `ml` extra)"
    if not info["cuda_available"]:
        return f"torch {info['torch']}: CUDA not available"
    return f"torch {info['torch']}: CUDA available, {info['gpu']}, {info['vram_gb']} GB"
