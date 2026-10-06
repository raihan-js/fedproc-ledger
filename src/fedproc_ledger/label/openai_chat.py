"""OpenAI chat backend for the panel (D-021: no Qwen / PRC-origin models in this project's labelling or judging).

Every call is logged with its token counts and an estimated cost; a hard cap on cumulative spend stops the run before
the call that would exceed it. Prices are list prices as I know them (USD per 1M tokens) and may be stale: the cap
carries a safety factor, and the logged token counts are the ground truth to reconcile against the usage page.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from fedproc_ledger.envfile import load_env, require

PRICES: dict[str, tuple[float, float]] = {  # model -> (input, output) USD per 1M tokens
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4o": (2.50, 10.00),
}
DEFAULT_CAP = 6.0  # owner credit was USD 6.89 on 2026-10-07; the rest is a buffer for stale prices
SAFETY = 1.5  # estimated costs are multiplied by this before they are compared with the cap
LEDGER = Path("data/logs/spend.jsonl")


class SpendCapExceeded(RuntimeError):
    pass


def spent(ledger: Path = LEDGER) -> float:
    if not ledger.exists():
        return 0.0
    return sum(float(json.loads(x)["usd_estimated"]) for x in ledger.read_text().splitlines() if x.strip())


def cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    if model not in PRICES:
        raise KeyError(f"no price known for {model}; add it to PRICES before using it")
    pin, pout = PRICES[model]
    return (prompt_tokens * pin + completion_tokens * pout) / 1e6


def strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """OpenAI strict structured outputs need additionalProperties=false and every property required."""
    s: dict[str, Any] = json.loads(json.dumps(schema))

    def fix(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object":
                node["additionalProperties"] = False
                node["required"] = list(node.get("properties", {}))
            for v in node.values():
                fix(v)
        elif isinstance(node, list):
            for v in node:
                fix(v)

    fix(s)
    return s


def make_openai_chat(
    schema: dict[str, Any],
    cap_usd: float | None = None,
    ledger: Path = LEDGER,
    transport: httpx.BaseTransport | None = None,
    base_url: str = "https://api.openai.com/v1",
) -> Callable[[str, list[dict[str, str]]], str]:
    load_env()
    if cap_usd is None:
        cap_usd = float(os.environ.get("OPENAI_SPEND_CAP", DEFAULT_CAP))
    key = require("OPENAI_API_KEY")
    client = httpx.Client(
        base_url=base_url, timeout=120.0, transport=transport, headers={"Authorization": f"Bearer {key}"}
    )
    lock = threading.Lock()
    body_schema = {"name": "labels", "strict": True, "schema": strict_schema(schema)}

    def chat(model: str, messages: list[dict[str, str]]) -> str:
        chars = sum(len(m["content"]) for m in messages)
        worst = cost(model, chars // 3 + 400, 1200) * SAFETY  # prompt tokens over-estimated, output at the 1,200 cap
        with lock:
            if spent(ledger) + worst > cap_usd:
                raise SpendCapExceeded(
                    f"cap ${cap_usd:.2f} would be exceeded (spent ${spent(ledger):.4f}, next call up to ${worst:.4f})"
                )
        r = client.post(
            "/chat/completions",
            json={
                "model": model,
                "messages": messages,
                "temperature": 0,
                "max_tokens": 1200,
                "response_format": {"type": "json_schema", "json_schema": body_schema},
            },
        )
        r.raise_for_status()
        data = r.json()
        use = data.get("usage", {})
        pt, ct = int(use.get("prompt_tokens", 0)), int(use.get("completion_tokens", 0))
        with lock:
            ledger.parent.mkdir(parents=True, exist_ok=True)
            with open(ledger, "a", encoding="utf-8") as f:
                row = {
                    "ts": datetime.now(UTC).isoformat(timespec="seconds"),
                    "model": model,
                    "prompt_tokens": pt,
                    "completion_tokens": ct,
                    "usd_estimated": cost(model, pt, ct) * SAFETY,
                }
                f.write(json.dumps(row) + "\n")
        return str(data["choices"][0]["message"]["content"])

    return chat
