# Pre-registration, round 3 (written 2026-10-07, after the frame was frozen and before any round-3 label, judge run or evaluation)

Why a third round: round 2 (D-032, D-033) became a development set once its errors were read and three rules were added to the pipeline
(paragraph (a) of 52.212-5, sub-items whose marker was lost, SF 1449 blocks 27a/27b; "rules v1.1", commit recorded in
`results/round3_manifest.json`). Model weights are **unchanged** (sha256 starts 9e9611a4, the round-1 file); only rules and the primary
aggregation changed. Weak labels from two LLM voters were tried for a v2 model and did not beat v1.1 on round 2 (D-034), so they are not used.
Round 3 is the first fresh test of v1.1.

## Frame (scripts/select_round3.py; list and sha256 in results/round3_docs_FROZEN.json, frozen before this text)
Pool: documents with a status-quo entry, not used in training, development, round 1, round 2 or the weak-label sample, with solicitation
numbers disjoint from all of them. Strata by distinct numbers: **S** 8 to 40; **M** 41 to 80 with at least 10 rule-decided checklist items;
**L** 81 to 150 with at least 10 rule-decided checklist items. 10 documents per stratum (30), at most 4 per department, at least 12 posted on or
after 2025-10-28 (RFO era). Seed 20261013.

## Gold
Labelled universe: distinct numbers with at least one mention **not** decided by a rule (source `model` in the v1.1 predictions). Stratum S in
full; strata M and L at most 20 numbers per document (uniform sample, seed 20261014). Three annotators, labels as words (BINDS, NOT,
REFERENCED, UNDECIDED): the coding agent (hand labels from the evidence sheets, before it sees any prediction or judge output), gpt-4o-mini and
gpt-4.1-mini with the instructions that contain the checkbox convention and amendment A2 of round 2 (`GUIDE_V2` in `scripts/ledger_judge.py`).
**Stated limit:** these instructions were written from the agent's conventions, so the three annotators are not independent readers of the
format. Primary gold: majority, binding set = BINDS; non-binding = NOT or REFERENCED (two of three); else undecided and excluded.

## Primary metric and baselines
Binding-set F1 over the labelled universe, micro over documents, cluster bootstrap over documents (10,000 resamples), paired bootstrap for
differences. Primary model configuration, fixed now (chosen on round 2): **max over mentions, q >= 0.5**. Baselines: B0 (status quo),
B0 minus empty-box clauses, B1, all-candidates. Per-stratum F1, specificity and recall reported.

## Hypotheses (numbers fixed now)
- **H1.** Model minus B1: F1 difference at least +0.10, interval excludes 0.
- **H2.** Model specificity at least 0.70 with recall at least 0.90, while B0 specificity is below 0.20.
- **H3.** Model minus B0 F1: lower interval bound above -0.03 (non-inferiority). Superiority only if the lower bound exceeds +0.01 **and** the point
  difference is positive on at least two of the three single-annotator golds.
- **H4.** Abstention: threshold chosen on the round-2 majority gold built with the corrected judge instructions (95% target, as in D-022) using
  v1.1 predictions; on round 3, coverage at least 0.60 and accuracy at least 0.92.
- **H5 (objective).** In strata M and L, at least 10% of B0's ledger entries are clauses whose every mention is a rule-decided empty-box item.
- **H6 (rule validity).** 60 mentions drawn at random (seed 11) from all rule-decided mentions of the 30 documents are read by the agent from the marked
  line; the rule must agree on at least 57.
All six are reported whether or not they hold.

## Known limits stated in advance
LLM annotators and an agent that also wrote the rules, not experts; numbers only; 30 documents with repeated templates; round 2 was used for
development, so round-3 gains are the only generalisation evidence; the annotator-independence limit above.
