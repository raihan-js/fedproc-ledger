# Pre-registration (template: fill in during Phase 6, commit before any test evaluation)

Status: **EMPTY**. Plan section 10.4. The commit hash of the filled-in version is recorded in `docs/decisions.md`.

## Primary metric
Document-level binding-set F1 (micro over documents) on `test_iid`; correct if `(number)` matches; strict variant also needs `alternate` and `cited_date`.

## Secondary metrics
(fill in: mention-level role macro-F1 and per-role F1, whole-ledger exact match, provision/clause split, candidate-generator recall, version-currency categories, downstream verdict resolution)

## Baselines
B0 VETR status quo, B1 rules, B2 LLM zero/few-shot (models pinned), B3 DeBERTa-v3-base window 512.

## Hypotheses (state thresholds as numbers before looking at test)
- H1 (fill in)
- H2 (fill in)
- H3 (fill in)

## Statistical tests
Cluster bootstrap over documents (10,000 resamples) for 95% CIs; paired bootstrap for model-vs-baseline differences. Multiple-comparison handling: (fill in).

## Frozen inputs
Split files and sha256 (fill in from `fl split`), OOD departments (chosen before any modelling), model and prompt versions.
