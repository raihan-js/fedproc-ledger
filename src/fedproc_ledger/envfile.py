"""Read secrets from .env (stdlib only). Values are never printed, logged or put in an exception message."""

from __future__ import annotations

import os
import re
from collections.abc import MutableMapping
from pathlib import Path

from fedproc_ledger.paths import ROOT

_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


class MissingSecret(RuntimeError):
    pass


def parse_env(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        m = _LINE.match(raw)
        if not m:
            continue
        key, val = m.group(1), m.group(2)
        if val[:1] in "\"'" and len(val) >= 2 and val[-1] == val[0]:
            val = val[1:-1]
        elif val.startswith("#"):
            val = ""  # `KEY=   # comment`: an empty value followed by a comment
        else:
            val = re.split(r"\s+#", val, maxsplit=1)[0].strip()  # `KEY=value   # comment`
        out[key] = val
    return out


def load_env(path: Path = ROOT / ".env", environ: MutableMapping[str, str] = os.environ) -> list[str]:
    """Put .env values into the environment without overriding values already set. Returns the names that were set."""
    if not path.exists():
        return []
    set_names = []
    for key, val in parse_env(path.read_text(encoding="utf-8")).items():
        if val and key not in environ:
            environ[key] = val
            set_names.append(key)
    return set_names


def require(name: str, environ: MutableMapping[str, str] = os.environ) -> str:
    val = environ.get(name, "")
    if not val:
        raise MissingSecret(f"{name} is not set (copy .env.example to .env and fill it in)")
    return val
