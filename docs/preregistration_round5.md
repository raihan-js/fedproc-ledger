# Pre-registration, round 5 (written 2026-10-07 after the frame was frozen; no round-5 prediction, label or judge output has been examined)

Why: round 4 (D-037) passed on rules v1.2. Exploratory work on rounds 2 to 4 (now all development data; D-038) found that a number-level
**stacker** (logistic regression over features aggregated from a number's mentions, trained on the agent's number labels of rounds 2 to 4) cut the
cross-validated error: AUC 0.982 against 0.949 for max-q, and a review queue of 14% of numbers holding 71% of the errors (max-q: 29% and 56%).
Round 5 is the first fresh test of the stacker. Frozen artefacts: role-model weights (sha256 9e9611a4...), rules v1.2, stacker `data/models/stacker_v3.pkl`
(hash in `results/round5_manifest.json`). Numbers decided only by rules keep their rule value (q 0 or 1); the stacker applies to numbers with at least one model-decided mention.

## Frame (scripts/select_round5.py; results/round5_docs_FROZEN.json)
As rounds 3 and 4, plus disjoint from round 4. Seed 20261017. After the exclusions only 10 M documents were eligible and the department cap left 4: the frame
has 24 documents (S 10, M 4, L 10; 17 posted on or after 2025-10-28). Stated before any label.

## Gold
As round 4: labelled universe = numbers with at least one mention decided by the model (source `model`); S in full, M and L at most 20 numbers per
document (seed 20261018); the agent labels by hand first; gpt-4o-mini and gpt-4.1-mini with `GUIDE_V2`; majority gold, binding set = BINDS.
Limit unchanged: the judges' instructions come from the agent's conventions. A second limit specific to this round: **the stacker was trained on the
agent's labels**, so agreement with the agent is no longer independent evidence of the stacker; the judge-only golds are reported for that reason.

## Primary configuration and baselines
Primary: **stacker q >= 0.5**. Secondary (reported, not primary): max-q >= 0.5 (round-4 configuration). Baselines B0, B0 minus empty-box clauses, B1, all-candidates.

## Hypotheses (numbers fixed now)
- **H1.** Stacker minus B1: F1 at least +0.10, interval excludes 0.
- **H2.** Stacker specificity at least 0.70 and recall at least 0.90 on the majority gold; B0 specificity below 0.20.
- **H3.** Stacker minus B0: lower bound above -0.03; superiority if the lower bound exceeds +0.01 and the point difference is positive on all three single golds.
- **H4 (review queue).** Numbers with stacker q strictly between 0.1 and 0.9: at most 25% of the labelled numbers, at least 60% of the stacker's errors on the majority gold,
  accuracy outside the queue at least 0.93.
- **H5 (stacker against max-q).** Paired F1 difference stacker minus max-q on the majority gold: the lower bound is above -0.02 (no loss), and on the two judge-only golds the point difference is not negative on both.
- **H6 (rule validity).** 60 rule-decided mentions drawn at random (seed 17) read by the agent: at least 57 agree.
- **H7 (objective).** In M and L documents at least 10% of B0's entries are empty-box clauses.
All are reported whether or not they hold.

## Known limits stated in advance
LLM annotators and an agent that wrote the rules and the stacker's training labels; 24 documents; M stratum 4 documents; numbers only.
