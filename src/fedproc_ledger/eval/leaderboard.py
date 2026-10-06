"""Every look at dev is a row: config hash, metrics and the number of looks so far (adaptive-overfitting guard)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fedproc_ledger.manifest import config_hash, git_state


def log_run(
    path: Path, name: str, config: dict[str, Any], metrics: dict[str, Any], split: str = "dev"
) -> dict[str, Any]:
    rows = read(path)
    entry = {
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "name": name,
        "split": split,
        "looks_at_split": 1 + sum(1 for r in rows if r["split"] == split),
        "config_hash": config_hash(config),
        "git": git_state(),
        "config": config,
        "metrics": metrics,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, default=float) + "\n")
    return entry


def read(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
