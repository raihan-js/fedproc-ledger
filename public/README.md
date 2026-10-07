---
license: apache-2.0
library_name: numpy
tags: [federal-procurement, far, dfars, clause-extraction, text-classification, legal-nlp]
---

# fedproc-ledger v1 — which solicitation clauses actually bind

A small (0.46 MB) classifier that decides, for each FAR/DFARS clause-number mention in a US federal solicitation, what role the mention plays: incorporated by reference, full text, selected checklist item, not selected, narrative mention, internal reference, and so on. A per-document aggregation over mentions gives the probability that the document *binds* the clause. The model never generates clause numbers: numbers come from regex candidates validated against the eCFR registry, and checklist boxes are decided by rule, not by the model.

- Weights: `fedproc_ledger_v1.npz` (numpy archive — no pickle, safe to load). Exported from the frozen research weights (sha256 `9e9611a4…`, fixed before the first test round); numpy-only inference matches the training-time model to 1e-9 (parity-tested).
- Inference: `inference.py` needs only numpy. CPU, milliseconds per document for the scorer; end-to-end latency is dominated by PDF extraction (about 115 ms per document in the research pipeline).
- Rules: checkbox states, the unconditional paragraph (a) of FAR 52.212-5, inherited sub-item states, SF 1449 block 27, bare clause lists, exclusion vetoes (v1.4, in the research repository).
- Research code (private while under review): `fl model train|predict` in the fedproc-ledger repository.

## Use

```python
import numpy as np
from inference import LedgerScorer
scorer = LedgerScorer("fedproc_ledger_v1.npz")
p = scorer.proba(feats, contexts)   # feats: [{feature: value}], contexts: [str]
bind = scorer.binding_prob(p)       # P(mention role is binding)
```

`feats` are the structural mention features from the research pipeline (box markers, section labels, line patterns); `contexts` are the mention windows. See the dataset (`raihan-js/fedproc-ledger-bench`, `mentions.parquet`) for the exact feature contract.

## Evidence (pre-registered rounds on fresh documents; labels from a coding agent and two OpenAI models, not legal experts)

| round | gold | model F1 vs status-quo regexes (B0) | specificity model vs B0 |
|---|---|---|---|
| frozen test (32 docs) | majority of agent + 2 judges | 0.912 vs 0.891, +0.020 [-0.005, +0.046] | 38% vs 4% |
| 3, fresh test of rules v1.1 (30 docs) | majority | 0.890 vs 0.778, +0.111 [+0.049, +0.181] | 84% vs 16% |
| 4, fresh test of rules v1.2 (26 docs) | majority | 0.921 vs 0.780, +0.142 [+0.085, +0.210] | 76% vs 10% |
| 5, second fresh test (24 docs) | majority | 0.926 vs 0.829, +0.097 [+0.040, +0.158] | 78% vs 19% |
| 6, fresh test of rules v1.3 (24 docs) | majority | 0.914 vs 0.807, +0.107 [+0.057, +0.161] | 73% vs 8% |
| 7, fresh test of rules v1.4 on the temporal hold-out (27 docs posted after the last acquisition day) | majority | 0.890 vs 0.806, +0.084 [+0.028, +0.143] | 70% vs 14% |

Without any annotator: about 13–14% of status-quo entries over the full corpus are clauses whose every mention is a checklist item with an empty box (20–31% in checklist-heavy documents).

## Known limits

No human expert labels; pooled pairwise annotator agreement is 75–82%, which bounds what any score against a judge majority can show. The model trades a small amount of recall for specificity. Numbers only: no alternates, dates or ranges. Not legal advice; do not use it to remove clauses silently. Full limitations, negative results and the pre-registration record are in the accompanying paper.
