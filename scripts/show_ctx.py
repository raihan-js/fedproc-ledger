"""Print full contexts for numbers of one round document: show_ctx.py ROUND DOC_INDEX number [number ...]"""

import sys
from pathlib import Path

from fedproc_ledger.label.commands import build_items

rnd, di = sys.argv[1], int(sys.argv[2])
doc = Path(f"data/interim/{rnd}_docs.txt").read_text().split()[di - 1]
for it in build_items(doc):
    if it["number"] in sys.argv[3:]:
        print(f"## {it['number']} | {' > '.join(it['breadcrumb'])[:90]}")
        print(it["context"][:900])
        print()
