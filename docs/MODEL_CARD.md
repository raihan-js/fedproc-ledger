---
license: other
library_name: scikit-learn
tags: [federal-procurement, far, dfars, clause-extraction, text-classification]
---
# fedproc-ledger role model (private research release, v0.1)

A small (0.86 MB) classifier that decides, for each FAR/DFARS clause-number mention in a US federal solicitation, what role the mention plays: incorporated by reference, full text, selected checklist item, not selected, narrative, internal reference and so on. A per-document noisy-OR over mentions gives the probability that the document *binds* the clause. The model never generates clause numbers: numbers come from regex candidates validated against the eCFR registry. Checklist boxes are decided by rule, not by the model.

- Weights: `role_model.pkl` (scikit-learn pickle; **load only from this repository**, pickles execute code). sha256 starts `9e9611a4…`, the hash frozen before the round-1 test run.
- Inference: CPU only, about 115 ms per document including parsing; no GPU, no LLM, no network.
- Rules: v1.4 (code in the repository; the weights file is unchanged since round 1).
- Code: private repository `raihan-js/fedproc-ledger` (`fl model train|predict`).

## Evidence (all from `results/*.json` in the code repository; LLM annotators, not legal experts)
| round | gold | model F1 vs status-quo regexes (B0) | specificity model vs B0 |
|---|---|---|---|
| 1, frozen test, as pre-registered (32 docs) | majority of agent + 2 judges | 0.912 vs 0.891, +0.020 [-0.005, +0.046] | 38% vs 4% |
| 1, corrected judge protocol (post-hoc) | same, word labels | 0.962 vs 0.939, +0.0227 [+0.00003, +0.0459] | 73% vs 8.5% |
| 2, checklist-heavy frame (36 docs), pre-registered | majority | 0.815 vs 0.918, **-0.103 [-0.185, -0.036]: H3 fails** | 68% vs 20% |
| 2, post-hoc judges told the checkbox convention | majority | 0.891 vs 0.844, +0.047 [-0.000, +0.096] | 78% vs 6% |
| 3, fresh test of rules v1.1 (30 docs), pre-registered | majority | 0.890 vs 0.778, +0.111 [+0.049, +0.181] | 84% vs 16% |
| **4, fresh test of rules v1.2 (26 docs), pre-registered** | majority | **0.921 vs 0.780, +0.142 [+0.085, +0.210]** (positive for all three annotators) | **76% vs 10%** (recall 0.940 vs 0.877) |
| 5, second fresh test (24 docs), pre-registered, stacker | majority | 0.926 vs 0.829, +0.097 [+0.040, +0.158] (positive for all three annotators; stacker = max-q within +0.004) | 78% vs 19% (recall 0.926) |
| **6, fresh test of rules v1.3 (24 docs), pre-registered, all six hypotheses hold** | majority | **0.914 vs 0.807, +0.107 [+0.057, +0.161]** (interval above zero for all three annotators) | **73% vs 8%** (recall 0.939) |
| **7, fresh test of rules v1.4 on the temporal hold-out (27 docs posted after the last acquisition day), pre-registered, all six hypotheses hold** | majority | **0.890 vs 0.806, +0.084 [+0.028, +0.143]** (positive on all three single annotators) | **70% vs 14%** (recall 0.903) |
Without any annotator: 13.5% of status-quo entries over 6,472 documents (25.4% in checklist-heavy documents) are clauses whose own checklist box is empty.

## Known limits
No human expert labels. Annotator readings of checkboxes differ strongly (round 2: judge-vs-agent kappa 0.05 and 0.21 before instructions stating the convention); pooled over rounds 2-6, pairwise annotator agreement is 75-82% (kappa 0.47-0.56), which bounds what any score against a judge majority can show. The model costs recall (about 1.4 points in round 1, about 10 in round 2) in exchange for specificity; calibration and abstention (pre-registered H4) did not meet their targets. Numbers only: no alternates, dates or ranges. Not legal advice; do not use it to remove clauses silently.
