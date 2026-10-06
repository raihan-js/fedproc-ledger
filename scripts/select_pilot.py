"""Pick the 20-document pilot (D-019): stratified, one document per solicitation, at least 6 from the RFO era. Seeded."""

import json
import random
from pathlib import Path

import pandas as pd

SEED, RFO = 20261006, "2025-10-28"
docs = pd.read_parquet("data/interim/documents.parquet").drop_duplicates("doc_id")
s = pd.read_parquet("data/processed/rules/_summary.parquet").merge(
    docs[["doc_id", "solicitation_number", "posted_date", "department"]], on="doc_id"
)
s["chk"] = s["roles"].map(lambda r: int(r.get("CHECKLIST_SELECTED") or 0) + int(r.get("CHECKLIST_NOT_SELECTED") or 0))
s["ibr"] = s["roles"].map(lambda r: int(r.get("INCORPORATED_BY_REFERENCE") or 0))
s["rfo_era"] = s["posted_date"].astype(str) >= RFO
s = s[(s.candidates >= 8) & (s.candidates <= 150)].drop_duplicates("solicitation_number")
rng = random.Random(SEED)


def take(frame: pd.DataFrame, n: int, chosen: set[str], need_rfo: int = 0) -> list[str]:
    ids = sorted(frame[~frame.doc_id.isin(chosen)].doc_id)
    rng.shuffle(ids)
    rfo = [i for i in ids if bool(frame.set_index("doc_id").loc[i, "rfo_era"])]
    out = rfo[:need_rfo]
    out += [i for i in ids if i not in out][: n - len(out)]
    return out


chosen: set[str] = set()
strata = {}
strata["checklist"] = take(s[s.chk >= 5], 8, chosen, 3)
chosen |= set(strata["checklist"])
strata["ibr"] = take(s[(s.ibr >= 10) & (s.chk < 5)], 6, chosen, 2)
chosen |= set(strata["ibr"])
strata["other"] = take(s[(s.chk < 5) & (s.ibr < 10)], 6, chosen, 1)
chosen |= set(strata["other"])
rfo_n = int(s[s.doc_id.isin(chosen)].rfo_era.sum())
info = (
    s.set_index("doc_id")
    .loc[sorted(chosen), ["candidates", "chk", "ibr", "posted_date", "department"]]
    .astype(str)
    .to_dict("index")
)
out = {"seed": SEED, "rfo_cutoff": RFO, "rfo_era_documents": rfo_n, "strata": strata, "info": info}
Path("results/pilot_docs.json").write_text(json.dumps(out, indent=1))
Path("data/interim/pilot_docs.txt").write_text("\n".join(sorted(chosen)) + "\n")
print(
    len(chosen),
    "documents;",
    rfo_n,
    "from the RFO era;",
    {k: len(v) for k, v in strata.items()},
    "candidates:",
    int(s[s.doc_id.isin(chosen)].candidates.sum()),
)
