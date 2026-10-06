"""The RFO layer of the registry: what the Revolutionary FAR Overhaul model deviation does to each Part 52 section.

eCFR carries the formal FAR text; the RFO model deviation (issued 2025-10-28, updated 2026-07-01, acquisition.gov)
reserves many classic clauses (52.212-5 among them) and adds new numbers. A solicitation under an RFO deviation can
cite either set, so the registry records, per FAR section, `rfo_status` (text | reserved | None when the model text does
not list it) and adds a row, status `rfo_only`, for each numbered section that exists in the model text but not in eCFR.
"""

from __future__ import annotations

import pandas as pd


def merge_rfo(registry: pd.DataFrame, rfo: pd.DataFrame) -> pd.DataFrame:
    """Idempotent: earlier `rfo_only` rows are dropped and recomputed."""
    reg = registry[registry["status"] != "rfo_only"].copy()
    rfo = rfo[rfo["number"].str.match(r"^52\.\d{3}-\d+$")].drop_duplicates("number").set_index("number")
    far = reg["regulation"] == "FAR"
    reg["rfo_status"] = None
    reg.loc[far, "rfo_status"] = reg.loc[far, "number"].map(rfo["rfo_status"])
    new = rfo[(rfo["rfo_status"] == "text") & ~rfo.index.isin(reg["number"])]
    if len(new):
        template = reg[far].iloc[0]
        rows = []
        for number, r in new.iterrows():
            rows.append(
                {
                    **{k: None for k in reg.columns},
                    "number": number,
                    "regulation": "FAR",
                    "regulation_name": template["regulation_name"],
                    "chapter": template["chapter"],
                    "part": "52",
                    "title": r["rfo_title"],
                    "kind": r.get("rfo_kind", "unknown"),
                    "kind_source": "rfo_model_text",
                    "prescribed_in": [],
                    "current_date": None,
                    "alternates": [],
                    "versions": [],
                    "status": "rfo_only",
                    "removed": False,
                    "has_prescription": True,
                    "source_range": None,
                    "rfo_status": "text",
                }
            )
        reg = pd.concat([reg, pd.DataFrame(rows)], ignore_index=True)
    return reg
