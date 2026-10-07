---
license: other
tags: [federal-procurement, far, dfars, clause-ledger]
---
# fedproc-ledger data (research release, v1.0)

- `mentions.parquet`: 685,079 clause-number mentions from 6,606 public SAM.gov solicitation documents with status-quo entries: doc_id, number, alternate, role, binding_prob, source (`model`, `box_rule`, `para_a_rule` or `text_rule`; rules v1.2, so it differs from the round-1 table in its box and rule counts), confidence, and a 300-character context snippet (personal-data patterns redacted at extraction). Roles and probabilities are **model output**, not labels.
- `results/`: gold label files (`ledger_gold_*.json`: development set, frozen test and rounds 2 to 7 including the agent, judge and majority files; labels BINDS/NOT/REFERENCED/UNDECIDED from the coding agent and two OpenAI models, no human annotators), evaluation outputs and the frozen document lists with sha256. Round 7 (27 documents posted 2026-09-30 to 2026-10-07, rules v1.4) is the temporal hold-out; the per-mention table refresh with v1.4 predictions is queued, so `mentions.parquet` stays on rules v1.2 for now.
Source documents are public US federal solicitation notices; this release contains derived tables and short snippets only (contact emails and phone numbers redacted, hardened against glued tokens in D-045). Released publicly by the CTO of Acu-Elligent LLC for research reproducibility alongside the paper.
