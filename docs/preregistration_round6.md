# Pre-registration, round 6 (written 2026-10-07 after the frame was frozen; no round-6 prediction, label or judge output examined)

Why: rules v1.3 (D-040: bare lists of clause numbers, "or FAR x, as applicable" alternative references) were written after reading the round-4 and round-5 errors,
so rounds 2 to 5 are development data. Round 6 is the first fresh test of v1.3. Frozen: role-model weights (sha256 9e9611a4...), rules v1.3 (commit in
`results/round6_manifest.json`), primary configuration **max over mentions, q >= 0.5**. The stacker is not used (D-039).

## Frame (scripts/select_round6.py; results/round6_docs_FROZEN.json)
As round 5 plus disjoint from round 5; seed 20261019. Only 6 M documents were eligible after the exclusions; the department cap left 4: 24 documents (S 10, M 4, L 10; 14 posted on or after 2025-10-28). Stated before any label.

## Gold
As rounds 4 and 5: labelled universe = numbers with at least one model-decided mention; S in full, M and L at most 20 numbers per document (seed 20261020); the agent labels by hand first;
gpt-4o-mini and gpt-4.1-mini with `GUIDE_V2`; majority gold, binding set = BINDS. Limit unchanged: the judges' instructions come from the agent's conventions.

## Hypotheses (numbers fixed now)
- **H1.** Model minus B1: F1 at least +0.10, interval excludes 0.
- **H2.** Specificity at least 0.70 and recall at least 0.90 on the majority gold; B0 specificity below 0.20.
- **H3.** Model minus B0: lower bound above -0.03; superiority if the lower bound exceeds +0.01 and the point difference is positive on all three single golds.
- **H4 (objective).** In strata M and L at least 10% of B0's entries are empty-box clauses.
- **H5 (rule validity).** 60 rule-decided mentions drawn at random (seed 19) read by the agent: at least 57 agree.
- **H6 (consistency).** The model's F1 on the majority gold is at least 0.88 (round 4: 0.921, round 5: 0.922), i.e. no deterioration beyond sampling noise.
The review-queue statistic is reported but is no longer a hypothesis (it failed in rounds 4 and 5).

## Known limits stated in advance
LLM annotators and an agent that wrote the rules; 24 documents; M stratum 4 documents; numbers only.
