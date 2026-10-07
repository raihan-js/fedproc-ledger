# Pre-registration, round 2 (written 2026-10-07, before any round-2 document is selected, predicted or labelled)

Why a second round: round 1 (docs/preregistration.md, D-028, D-031) used a frame (8 to 40 distinct numbers per document) that
excludes the checklist-heavy documents where the status quo over-counts, and a judge protocol with a label-letter collision.
Round 2 fixes both. The model is **not retrained**: same frozen weights as round 1 (sha256 in results/test_run_manifest.json).

## Frame and sampling (scripts/select_round2.py; list and sha256 written to results/round2_docs_FROZEN.json before labelling)
Pool: documents with at least one status-quo entry that were not used for training, development or round 1, and whose solicitation is
not shared with any of them. Strata by distinct clause numbers per document: **S** 8 to 40 numbers (no checklist requirement);
**M** 41 to 80 numbers with at least 10 rule-decided checklist items; **L** 81 to 150 numbers with at least 10 rule-decided checklist
items. 12 documents per stratum, at most 4 per department overall, at least 12 of the 36 posted on or after 2025-10-28. Seed 20261010.

## Gold
Labelled universe: distinct numbers whose mentions are **not all decided by the checkbox rule** (those are objective and reported
separately). Three blind annotators, labels as words: BINDS, NOT, REFERENCED, UNDECIDED (docs/annotation_guidelines.md; letters are not
used because documents print letters such as "R"): the coding agent, gpt-4o-mini, gpt-4.1-mini. Sheets show up to 3 contexts per number,
each with the marked line, one line before and one after (lines cut at 90 characters), and the two nearest headings. Primary gold: majority; **binding set = BINDS**;
non-binding = NOT or REFERENCED (two of three), else undecided and excluded. Applicable set (BINDS or REFERENCED) is secondary. The agent
labels first, without seeing predictions or judge output.

## Primary metric and baselines
Document-level binding-set F1 over the labelled universe, micro over documents, cluster bootstrap over documents (10,000 resamples), paired
bootstrap for differences. Baselines: B0 (status quo), B0 minus empty-box clauses, B1, all-candidates. Also reported, per stratum: F1,
specificity, recall.

## Hypotheses (numbers fixed now)
- **H1.** Model minus B1: F1 difference at least +0.10, interval excludes 0.
- **H2.** On the labelled universe, model specificity at least 0.60 with recall at least 0.90, while B0 specificity is below 0.20.
- **H3 (non-inferiority and a superiority bar).** Model minus B0 F1: lower interval bound above -0.03. Superiority is claimed only if the
  lower bound exceeds +0.01 **and** the point difference is positive on at least two of the three single-annotator golds.
- **H4.** Abstention: threshold chosen on round-1 corrected majority gold (95% target, as in D-022); on round 2, coverage at least 0.50 and
  accuracy at least 0.90.
- **H5 (objective, no annotator).** In strata M and L, at least 10% of B0's ledger entries are clauses whose every mention is a
  rule-decided empty-box item (median over documents reported too).
- **H6 (rule validity).** On the labelled universe the checkbox rule is not used; separately, 40 randomly drawn rule-decided items
  (seed 7) are read by the agent and the rule must agree on at least 38.
All six are reported whether or not they hold.

## Known limits stated in advance
LLM annotators, not experts; numbers only (no alternates, dates, ranges); 36 documents with repeated templates; model frozen, so this
round cannot show improvement over round 1, only generalisation to a better frame.

## Amendment A1 (2026-10-07, before any round-2 label existed)
Sheets changed from up to 4 contexts per number (105-character lines) to up to 3 contexts (90-character lines) to keep the labelling load reliable; nothing else changed. The frame (results/round2_docs_FROZEN.json) was frozen in commit 5448a6d and is untouched.
