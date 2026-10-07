# Pre-registration, reviewer gold (written 2026-10-07 after the frame was frozen; no reviewer has seen the sheets)

Why: every gold so far comes from the coding agent (who wrote the rules) and two OpenAI judges (whose instructions come from the agent). The VETR reviewer gold is the first independent check and the acceptance gate for any customer-visible use.

## Frame (scripts/select_reviewers.py; results/reviewer_docs_FROZEN.json)
200 documents (S 80, M 50, L 70; 113 posted on or after 2025-10-28), disjoint from every training, development and round 2-7 document and solicitation; seed 20261023. Sample: S in full, M/L at most 12 numbers per document (seed 20261024): 3,110 sampled numbers of 9,566 in the labelled universe (numbers with at least one model-decided mention). Blind sheets (no predictions), `docs/REVIEWER_GUIDE.md`, intake validator `scripts/reviewers_intake.py`.

## Gold
Two or more VETR reviewers label independently; disagreements resolved by majority, ties broken by a third read. Reviewer-vs-reviewer agreement (Cohen's kappa on role, binding-set Jaccard) is reported before any model score. Primary configuration, unchanged: max over mentions, q >= 0.5, rules v1.4, weights 9e9611a4.

## Acceptance criteria (fixed now)
- **A1 (non-inferiority):** model minus B0 binding-set F1, lower 95% bound above -0.03 on the reviewer majority gold.
- **A2 (recall guard):** model recall within 3 points of B0 recall on the same gold.
- **A3 (specificity):** model specificity at least 0.50 (reviewers are expected to mark more narrative references non-binding than the LLM judges did, which lowers everyone's precision; the specificity bar is set below the round-7 value for that reason).
- If A1-A3 hold: shadow mode (contract section 8) may begin. If any fails: no customer-visible use; the errors become the v1.5 development set and a new reviewer round is drawn.

## Known limits stated in advance
Reviewers are VETR staff, not contracting officers; one page of guidance, not the full annotation manual. 3,110 numbers is about 25 reviewer-hours.
