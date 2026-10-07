"""Majority golds for the frozen test set, as pre-registered: three annotators (agent, gpt-4o-mini, gpt-4.1-mini), labels B/N/R/U.
binding gold:    B if >= 2 say B; non-binding (N) if >= 2 say N or R; else U.
applicable gold: B (applicable) if >= 2 say B or R; N if >= 2 say N; else U."""

import collections
import json
import sys
from pathlib import Path

TAG = (
    sys.argv[1] if len(sys.argv) > 1 else "test"
)  # test = original judge run; test_v2 = judges re-run with unambiguous label words (D-031)

a = json.loads(Path("results/ledger_gold_test_agent.json").read_text())["gold"]
j1 = json.loads(Path(f"results/ledger_gold_{TAG}_judge_gpt-4o-mini.json").read_text())["gold"]
j2 = json.loads(Path(f"results/ledger_gold_{TAG}_judge_gpt-4.1-mini.json").read_text())["gold"]
out = {"binding": {}, "applicable": {}}
stats = collections.Counter()
for d in a:
    out["binding"][d], out["applicable"][d] = {}, {}
    for n, v in a[d].items():
        votes = [v, j1[d].get(n, "U"), j2[d].get(n, "U")]
        c = collections.Counter(votes)
        nb = c["B"]
        bind = "B" if nb >= 2 else ("N" if c["N"] + c["R"] >= 2 else "U")
        app = "B" if c["B"] + c["R"] >= 2 else ("N" if c["N"] >= 2 else "U")
        out["binding"][d][n], out["applicable"][d][n] = bind, app
        stats["binding_" + bind] += 1
        stats["applicable_" + app] += 1
print(dict(stats))
for k, g in out.items():
    Path(f"results/ledger_gold_{TAG}_majority_{k}.json").write_text(
        json.dumps({"annotator": f"majority of three, {k} (see scripts/test_gold.py)", "gold": g})
    )
