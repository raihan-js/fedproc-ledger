"""Helper for hand labelling: python scripts/round2_put.py DOC "id:code id:code ..." (ids are the original [doc.k] indices)."""

import json
import sys
from pathlib import Path

P = Path("data/audit/round7_labels_agent_part.json")
lab = json.loads(P.read_text()) if P.exists() else {}
doc, spec = sys.argv[1], sys.argv[2]
for pair in spec.split():
    k, c = pair.split(":")
    assert c in "BNRU", pair
    lab[f"{doc}.{k}"] = c
P.write_text(json.dumps(lab))
print(len(lab), "labels saved")
