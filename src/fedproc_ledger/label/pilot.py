"""Pilot report (D-019): B0 and B1 against the panel's ledger, and the panel against objective checkbox truth.

Slice A (no LLM): candidates on a checklist line whose box state is known (⟦X⟧ or ⟦ ⟧). B1 reads the same glyphs, so
slice A cannot score B1 (circular); it scores the panel members, and later the trained model.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

import numpy as np

from fedproc_ledger.eval import metrics as M
from fedproc_ledger.rules.baseline import BINDING, EXCLUDED, NOT_SELECTED, SELECTED

Key = tuple[str, str | None]


def panel_ledger(rows: Iterable[Mapping[str, Any]], alt: Mapping[str, str | None]) -> tuple[set[Key], set[str]]:
    """Ledger from adjudicated (non-split) mentions, and the numbers that have a split mention (uncertain)."""
    bind: dict[Key, bool] = defaultdict(bool)
    excluded: set[str] = set()
    uncertain: set[str] = set()
    for r in rows:
        if r["tier"] == "split":
            uncertain.add(r["number"])
            continue
        if r["role"] == EXCLUDED:
            excluded.add(r["number"])
        if r["role"] in BINDING:
            bind[(r["number"], alt.get(r["cand_id"]))] = True
    return {k for k in bind if k[0] not in excluded}, uncertain


def slice_a_truth(box_marker: str | None, in_checklist_item: bool) -> str | None:
    """SELECTED / NOT_SELECTED for the first number of a list item inside a checklist clause (52.212-5 and the like)
    whose line starts with a known box glyph; None otherwise. Boxes elsewhere (SF 1449 block 27 and so on) are not
    items of a checklist, so their glyph does not decide a role."""
    if not in_checklist_item or not box_marker:
        return None
    return {"⟦X⟧": SELECTED, "⟦ ⟧": NOT_SELECTED}.get(box_marker)


_ITEM = re.compile(
    r"^\s*⟦[X ]⟧\s*(?:\(\w{1,3}\)\s*)?"
    r"(?:Alternate\s+[IVXLC]+\s*(?:\([^)]*\)\s*)?(?:of\s+)?)?"
    r"(?:FAR\s+|DFARS\s+)?\d{2,4}\.\d{3}-\d{1,4}",
    re.I,
)


def checklist_item_keys(pages: Iterable[tuple[int, str]]) -> set[tuple[int, int]]:
    """(page, line_no) of checklist item lines: a box, an optional "(1)" or "Alternate I of", then the clause number
    straight away. A local rule on the extracted text, independent of the section detector. SF 1449 block 27 lines
    ("⟦X⟧ 27a. SOLICITATION INCORPORATES ...") do not match."""
    return {(pg, i) for pg, text in pages for i, line in enumerate(text.split("\n")) if _ITEM.match(line)}


def role_agreement(pred: Sequence[str], truth: Sequence[str]) -> dict[str, float]:
    n = len(truth)
    ok = sum(p == t for p, t in zip(pred, truth, strict=True))
    binding = sum((p in BINDING) == (t in BINDING) for p, t in zip(pred, truth, strict=True))
    return {
        "n": float(n),
        "role_agreement": ok / n if n else float("nan"),
        "binding_agreement": binding / n if n else float("nan"),
    }


def score_systems(per_doc: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """per_doc[doc] = {"gold": set, "uncertain": set, "systems": {name: set}}; certain numbers only."""
    out: dict[str, Any] = {}
    names = sorted({n for d in per_doc.values() for n in d["systems"]})
    gold = [{k for k in d["gold"] if k[0] not in d["uncertain"]} for d in per_doc.values()]
    for n in names:
        pred = [{k for k in d["systems"][n] if k[0] not in d["uncertain"]} for d in per_doc.values()]
        counts = M.ledger_counts(pred, gold)
        out[n] = {**M.micro_f(counts), "ci_f1": M.cluster_bootstrap(counts, n_boot=2000)}
    return out


def decide(b0_precision: float, b1_f1: float) -> str:
    """Plan 9.5 go/no-go, evaluated against the panel (not human gold)."""
    if b0_precision < 0.85 or b1_f1 < 0.90:
        return "GO_MODEL: a learned model has room to improve (B0 over-counts or B1 is under 0.90)"
    return "PIVOT: rules already near the panel; the contribution is the corpus and the findings"


def dumps(x: Any) -> str:
    return json.dumps(x, indent=1, default=lambda o: float(o) if isinstance(o, np.floating | np.integer) else list(o))
