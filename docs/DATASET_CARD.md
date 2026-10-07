---
license: other
tags: [federal-procurement, far, dfars, clause-ledger]
---
# fedproc-ledger data (private research release, v0.1)

- `mentions.parquet`: 685,079 clause-number mentions from 6,606 public SAM.gov solicitation documents with status-quo entries: doc_id, number, alternate, role, binding_prob, source (`box_rule` or `model`), confidence, and a 300-character context snippet (personal-data patterns redacted at extraction). Roles and probabilities are **model output**, not labels.
- `results/`: gold label files (`ledger_gold_*.json`: development set, round-1 test, round-2; labels BINDS/NOT/REFERENCED/UNDECIDED from the coding agent and two OpenAI models, no human annotators), evaluation outputs and the frozen document lists with sha256.
Source documents are public notices; this release contains derived tables and short snippets only. Company permission to publish is still outstanding, so the repository is private.
