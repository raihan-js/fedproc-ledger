# Pre-registration, round 7 (written 2026-10-07 after the frame was frozen; no round-7 prediction, label or judge output examined)

Why: rules v1.4 (D-043: `excluded_ids` veto for explicitly deleted/excluded clauses, "refer to / comply with the clause"
narrative rule) were written after reading the round-6 errors, so rounds 2 to 6 are development data for v1.4
(dev F1 vs B0 on the majority gold: r3 +0.136, r4 +0.155, r5 +0.098, r6 +0.112; r2 -0.071 on the judge-dominated gold).
Round 7 is the first fresh test of v1.4. Frozen: role-model weights (sha256 9e9611a4...), rules v1.4 (commit in
`results/round7_manifest.json`), primary configuration **max over mentions, q >= 0.5**. The stacker is not used (D-039).

## Frame (scripts/select_round7.py; results/round7_docs_FROZEN.json)
Temporal hold-out (D-042): all 27 documents come from the newer acquisition (posted 2026-09-30 to 2026-10-07, after the
last acquisition day 2026-09-29), disjoint from every training, development and round 2-6 document and solicitation;
S 10, M 7, L 10 (M: all 7 eligible); seed 20261021. Stated before any label.

## Gold
As rounds 4 to 6: labelled universe = numbers with at least one model-decided mention; S in full, M and L at most 20 numbers
per document (seed 20261022); the agent labels by hand first; gpt-4o-mini and gpt-4.1-mini with `GUIDE_V2` (word labels,
checkbox convention and A2); majority gold, binding set = BINDS. Limit unchanged: the judges' instructions come from the
agent's conventions.

## Hypotheses (numbers fixed now)
- **H1.** Model minus B1: F1 at least +0.10, interval excludes 0.
- **H2.** Specificity at least 0.70 and recall at least 0.90 on the majority gold; B0 specificity below 0.20.
- **H3.** Model minus B0: lower bound above -0.03; superiority if the lower bound exceeds +0.01 and the point difference is positive on all three single golds.
- **H4 (objective).** In strata M and L at least 10% of B0's entries are empty-box clauses.
- **H5 (rule validity).** 60 rule-decided mentions drawn at random (seed 23) read by the agent: at least 57 agree.
- **H6 (consistency).** The model's F1 on the majority gold is at least 0.88 (rounds 4-6: 0.921, 0.922, 0.914), i.e. no deterioration beyond sampling noise.
The review-queue statistic is reported but is not a hypothesis (it failed in rounds 4 and 5).

## Known limits stated in advance
LLM annotators and an agent that wrote the rules; 27 documents from a one-week posting window (template repetition likely);
M stratum 7 documents; numbers only.
