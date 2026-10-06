"""Every pipeline step writes a manifest: inputs, outputs, git SHA, config hash, timestamp (plan section 3)."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fedproc_ledger.paths import ROOT


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def config_hash(config: dict[str, Any]) -> str:
    """Stable hash of a config: canonical JSON (sorted keys, no whitespace)."""
    canon = json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def git_state(repo: Path = ROOT) -> dict[str, Any]:
    def run(*args: str) -> str | None:
        r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else None

    sha = run("rev-parse", "HEAD")
    status = run("status", "--porcelain")
    return {"sha": sha, "dirty": bool(status) if status is not None else None}


def _describe(paths: list[Path]) -> list[dict[str, Any]]:
    out = []
    for p in paths:
        p = Path(p)
        if p.is_file():
            out.append({"path": str(p), "sha256": sha256_file(p), "bytes": p.stat().st_size})
        else:
            out.append({"path": str(p), "sha256": None, "bytes": None, "missing": not p.exists()})
    return out


def write_manifest(
    step: str,
    inputs: list[Path],
    outputs: list[Path],
    config: dict[str, Any],
    out: Path,
    extra: dict[str, Any] | None = None,
    repo: Path = ROOT,
) -> dict[str, Any]:
    """Write `out` (JSON) and return the manifest. Call after the outputs exist."""
    manifest = {
        "step": step,
        "timestamp_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "git": git_state(repo),
        "config_hash": config_hash(config),
        "config": config,
        "inputs": _describe(inputs),
        "outputs": _describe(outputs),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        **(extra or {}),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest
