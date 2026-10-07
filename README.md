# fedproc-ledger

Which FAR/DFARS clauses actually bind a US federal solicitation, and how (incorporated by reference, full text, selected in a checklist), with a probability and the evidence lines. A mention-role classifier over regex clause candidates, validated against the eCFR registry; box states are decided by rule.

**Status (2026-10-07): research prototype, nothing published.** Numbers below are generated from `results/*.json` by `scripts/make_results_md.py`; the annotators of every gold set are LLM agents, not procurement experts, and the evaluation frame under-represents checklist-heavy documents (see `docs/decisions.md`, D-028).

## Headline
<!-- headline:start -->
- Frozen test (32 documents, 679 labelled numbers, LLM annotators), as pre-registered: F1 0.912 for the model vs 0.891 for the status-quo regexes (difference +0.020, interval [-0.005, +0.046]: non-inferior, **not shown better**); specificity 38% vs 4%.
- After correcting a label-letter collision in the judge protocol (post-hoc, D-031): F1 0.962 vs 0.939 (lower bound +0.00003, so no superiority claim), specificity 73% vs 8%; H2 holds on the corrected gold.
- Objective, annotator-free: **13.5%** of status-quo ledger entries are clauses whose own checklist box is empty (2247 of 2648 documents with a decided checklist).
- Pre-registered hypotheses as originally scored: H1 holds, H2 FAILS, H3 holds as non-inferiority only, H4 FAILS. Full tables: [`docs/RESULTS.md`](docs/RESULTS.md).
<!-- headline:end -->

## Read next
- Results tables: [`docs/RESULTS.md`](docs/RESULTS.md) · decisions and every correction: [`docs/decisions.md`](docs/decisions.md) · pre-registration: [`docs/preregistration.md`](docs/preregistration.md) · annotation guidelines: [`docs/annotation_guidelines.md`](docs/annotation_guidelines.md)
- Integration proposal for VETR: [`docs/INTEGRATION_CONTRACT.md`](docs/INTEGRATION_CONTRACT.md) · plan: [`docs/PLAN.md`](docs/PLAN.md) · where we are: [`docs/STATE.md`](docs/STATE.md) · rules for contributors and agents: [`CLAUDE.md`](CLAUDE.md)

## Reproduce
```bash
uv sync --extra ml --group dev
uv run pytest -q
uv run fl --help            # acquire, registry, extract, rules, label, model
uv run fl model train && uv run fl model predict
uv run python scripts/ledger_eval.py results/ledger_gold_test_majority_binding.json
uv run python scripts/make_results_md.py
```
Raw documents and the trained model are not in the repository (`data/` is git-ignored).

Not legal advice and not a compliance determination. Licence: Apache-2.0.
