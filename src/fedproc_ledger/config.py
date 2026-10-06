"""Configs are TOML files in configs/ (stdlib tomllib; no extra dependency)."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from fedproc_ledger.manifest import config_hash
from fedproc_ledger.paths import CONFIGS


def load_config(name_or_path: str | Path) -> dict[str, Any]:
    p = Path(name_or_path)
    if not p.suffix:
        p = CONFIGS / f"{name_or_path}.toml"
    with open(p, "rb") as f:
        cfg = tomllib.load(f)
    cfg["_hash"] = config_hash({k: v for k, v in cfg.items() if k != "_hash"})
    return cfg
