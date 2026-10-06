"""Independent labeller check: an OpenAI model gets the same blind evidence sheets and decides B / N / U per number.
Agreement with the agent gold (accuracy, Cohen's kappa) estimates how reliable the gold is. Never sees model output."""

import collections
import json
import sys
from pathlib import Path

from fedproc_ledger.eval.leaderboard import log_run
from fedproc_ledger.label import panel as P
from fedproc_ledger.label.commands import build_items
from fedproc_ledger.label.openai_chat import make_openai_chat, spent
from fedproc_ledger.paths import RESULTS

GUIDE = """You decide, for each clause number in a US federal solicitation or contract, whether the document BINDS it.
B = binds: listed as incorporated by reference, its full text is included, it is a selected/checked item, or the text states that it applies/is included in this contract.
N = does not bind: only cited or explained inside other clause text or narrative ("in accordance with FAR x"), a table of contents entry, an unselected/unchecked item, "not applicable", or not a real clause number (a fragment).
U = you cannot decide from the evidence shown.
Each number comes with up to three contexts (H = nearest heading; the number is marked >>> <<<). Answer with JSON only."""
SCHEMA = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"k": {"type": "string"}, "v": {"type": "string", "enum": ["B", "N", "U"]}},
                "required": ["k", "v"],
            },
        }
    },
    "required": ["verdicts"],
}


def sheet(doc: str) -> dict[str, str]:
    by: dict[str, list[dict]] = collections.OrderedDict()
    for it in build_items(doc):
        by.setdefault(it["number"], []).append(it)
    out = {}
    for n, ms in by.items():
        lines = [f"number {n} ({len(ms)} mentions)"]
        for it in ms[:3]:
            ctx = it["context"].split("\n")
            idx = next((i for i, x in enumerate(ctx) if ">>>" in x), len(ctx) - 1)
            seg = " / ".join(x[:110] for x in ctx[max(0, idx - 1) : idx + 1])
            h = it["breadcrumb"][-1][:40] if it["breadcrumb"] else ""
            lines.append(f"  - H:{h} | {seg}")
        out[n] = "\n".join(lines)
    return out


def main(model: str) -> None:
    gold = json.loads(Path("results/ledger_gold_agent_v0.json").read_text())["gold"]
    chat = make_openai_chat(SCHEMA)
    cache = P.Cache(Path("data/interim/judge_cache.jsonl"))
    pairs = []
    judged: dict[str, dict[str, str]] = {}
    for doc, labels in gold.items():
        sh = sheet(doc)
        nums = [n for n in labels if n in sh]
        for i in range(0, len(nums), 12):
            chunk = nums[i : i + 12]
            body = "\n\n".join(f"[{n}]\n{sh[n]}" for n in chunk)
            msgs = [
                {"role": "system", "content": GUIDE},
                {"role": "user", "content": body + '\n\nReturn {"verdicts":[{"k":<number>,"v":"B|N|U"}]}'},
            ]
            key = P.Cache.key(model, msgs)
            text = cache.get(key)
            if text is None:
                text = chat(model, msgs)
                cache.put(key, text)
            got = {e["k"]: e["v"] for e in json.loads(text).get("verdicts", [])}
            pairs += [(labels[n], got.get(n, "U")) for n in chunk]
            judged.setdefault(doc, {}).update({n: got.get(n, "U") for n in chunk})
    dec = [(a, b) for a, b in pairs if a in "BN" and b in "BN"]
    acc = sum(a == b for a, b in dec) / len(dec)
    pa = sum(a == "B" for a, _ in dec) / len(dec)
    pb = sum(b == "B" for _, b in dec) / len(dec)
    pe = pa * pb + (1 - pa) * (1 - pb)
    kappa = (acc - pe) / (1 - pe)
    both_u = sum(1 for a, b in pairs if a == "U" or b == "U")
    res = {
        "n_pairs": len(pairs),
        "n_decided_both": len(dec),
        "agreement": acc,
        "kappa": kappa,
        "judge_binding_rate": pb,
        "gold_binding_rate": pa,
        "any_U": both_u,
    }
    print(
        model,
        {k: round(v, 3) if isinstance(v, float) else v for k, v in res.items()},
        "| spent est $",
        round(spent(), 3),
    )
    Path(f"results/ledger_gold_judge_{model}.json").write_text(json.dumps({"annotator": model, "gold": judged}))
    log_run(
        RESULTS / "leaderboard.jsonl",
        f"ledger-label-check {model}",
        {"model": model},
        res,
        split="ledger-gold-v0-reliability",
    )


if __name__ == "__main__":
    main(sys.argv[1])
