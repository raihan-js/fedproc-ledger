# Pre-registration (filled 2026-10-07, before any frozen test document is labelled or scored)

Status: **FILLED**. The commit that contains this file is recorded in `docs/decisions.md` (D-025). Anything changed after
that commit is reported as a deviation.

## Test set
`results/ledger_test_docs_FROZEN.json`: 32 documents (seed 20261009; no solicitation overlap with any document used for training,
for the 25 development documents, or for audit sampling; at most 3 per department; 13 departments), sha256
`175b90d39c8eeb25...` in the file. These documents must not be opened, labelled or predicted before the final run. The 25
development documents (`results/ledger_gold_docs.json`) and all earlier numbers (D-020 to D-023) are development results.

## Primary metric
Document-level binding-set F1 over distinct clause numbers (micro over documents), restricted to numbers labelled B or N; U is
excluded. Gold for the test set: the **majority of three blind annotators** (the coding agent, gpt-4o-mini, gpt-4.1-mini; B or N
needs two of three, U votes ignored), using the labels B / N / R / U of `docs/annotation_guidelines.md`; **binding set = B**.
Each single annotator's gold is also reported, and the applicable set (B or R) is secondary.

## Secondary metrics
Precision, recall, F2, specificity (non-binding numbers left out), accuracy; abstention coverage and accuracy at the
dev-chosen threshold; calibration error of the binding probability on test mentions where the agent labelled them; per-department
results; agreement (kappa) among the three annotators.

## Baselines
B0 (VETR status quo regexes, registry-filtered), B1 rules, all-candidates (every number found binds). B2 LLM zero-shot is not run:
the dev bake-off (D-021, 52% role agreement at best) already shows it far below the trained model on mentions.

## Hypotheses (numbers fixed before looking at the test set)
- **H1.** Model minus B1: F1 difference at least +0.10 and the 95% paired-bootstrap interval excludes 0. (Dev: +0.17 to +0.24 on every gold.)
- **H2.** Model specificity at least 0.60 while recall stays at least 0.90, where B0 specificity is below 0.20. (Dev majority gold: 0.76 and 0.92; B0 0.105.)
- **H3 (non-inferiority, deliberately modest).** Model F1 minus B0 F1 has a lower interval bound above -0.03. (Dev majority gold: +0.035 [-0.014, +0.084].) A superiority claim over B0 is made only if the lower bound exceeds 0.
- **H4.** At the abstention threshold chosen on the development set, the share of numbers given a verdict is at least 0.85 and their accuracy at least 0.90 (dev: 0.92 coverage at 0.905 accuracy, D-022).
All four are reported whether or not they hold.

## Statistical tests
Cluster bootstrap over documents (10,000 resamples) for 95% intervals; paired bootstrap for model-vs-baseline differences on the
same resamples. Four hypotheses, no correction applied (each is a separate pre-stated claim); no claim rests on a single interval.

## Model and procedure
Final model = the classifier of `fl model train` on all labelled mentions from non-test documents (development documents may be
added to training after the development numbers are frozen), temperature fitted on grouped out-of-fold scores, ledger probability =
noisy-OR over mentions with the exclusion factor, binding if q >= 0.5. Box-glyph item lines are decided by rule. No test document
is used for any choice; no model change after the test labels exist.

## Known limits stated in advance
Annotators are LLM agents, not procurement experts; labels differ by annotator exactly on referenced-requirement narrative; the
effective sample is smaller than 32 because templates repeat; numbers only (no alternates or dates); ranges not expanded.
