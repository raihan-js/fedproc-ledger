# Pre-registration, round 4 (written 2026-10-07 after the frame was frozen and before any round-4 prediction was examined, label or judge run)

Why a fourth round: round 3 (D-035) was the first fresh test of rules v1.1. Its errors, and those of round 2, were then read and used to write
rules v1.2 (D-036: paragraph (a) of 52.212-5 with non-breaking spaces and lost markers, conditional-certificate / definition / paragraph-reference /
"is applicable" wordings, typed "XXX" marks). Rounds 2 and 3 are therefore development sets. Model weights are unchanged (sha256 begins 9e9611a4).
Round 4 is the first test of v1.2. No other change is made between now and the freeze.

## Frame (scripts/select_round4.py; list and sha256 in results/round4_docs_FROZEN.json)
Same rules as round 3 (pool disjoint from training, development, rounds 1 to 3 and the weak-label sample, distinct solicitation numbers, strata S/M/L by
distinct numbers with at least 10 rule-decided checklist items in M and L, at most 4 documents per department, at least 12 posted on or after
2025-10-28). Seed 20261015. **Deviation from the plan of 10 per stratum:** after the exclusions only 16 M documents were eligible and the department
cap left 6, so the frame has 26 documents (S 10, M 6, L 10; 16 in the RFO era).

## Gold
Same as round 3: labelled universe = numbers with at least one mention not decided by a rule (source `model` in the v1.2 predictions); S in full, M and L at
most 20 numbers per document (seed 20261016). Annotators: the coding agent (hand labels, before seeing any prediction or judge output), gpt-4o-mini and
gpt-4.1-mini with `GUIDE_V2`. Primary gold: majority, binding set = BINDS, non-binding = NOT or REFERENCED, else undecided. **Stated limit (unchanged):** the
judge instructions come from the agent's conventions, so the annotators are not independent readers of the format.

## Primary metric and baselines
Binding-set F1, micro over documents, cluster bootstrap (10,000 resamples), paired bootstrap for differences; primary configuration **max over mentions,
q >= 0.5**. Baselines B0, B0 minus empty-box clauses, B1, all-candidates; per stratum and per annotator results reported.

## Hypotheses (numbers fixed now)
- **H1.** Model minus B1: F1 difference at least +0.10, interval excludes 0.
- **H2.** Model specificity at least 0.70 **and** recall at least 0.90 on the majority gold; B0 specificity below 0.20.
- **H3.** Model minus B0 F1: lower bound above -0.03 (non-inferiority); superiority only if the lower bound exceeds +0.01 and the point difference is positive
  on at least two of the three single-annotator golds.
- **H4 (replaced; the round-3 coverage form failed).** Review queue: the numbers with q strictly between 0.1 and 0.9 are at most 45% of the labelled
  numbers and contain at least 60% of the model's errors on the majority gold; accuracy outside the queue is at least 0.93.
- **H5 (objective).** In strata M and L at least 10% of B0's ledger entries are empty-box clauses.
- **H6 (rule validity).** 60 rule-decided mentions drawn at random (seed 13) are read by the agent from the marked line; at least 57 agree.
All six are reported whether or not they hold.

## Known limits stated in advance
LLM annotators and an agent that also wrote the rules; 26 documents with repeated templates; M stratum small; numbers only; no alternates, dates or ranges.
