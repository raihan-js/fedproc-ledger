# Which clauses bind? Auditing a regex clause ledger on 925 US federal solicitations

*Draft v0.1, 2026-10-07. Numbers are copied from `docs/RESULTS.md` (generated from `results/*.json`); decisions D-019 to D-028 in `docs/decisions.md` record every correction. Not for circulation before the company's permission to publish is confirmed.*

## Abstract
Compliance tools for federal contracting commonly build a "clause ledger" by finding FAR and DFARS clause numbers in a solicitation with regular expressions. We ask how well that status quo answers the question a contracting team actually has: which of those clauses *bind* the contract? On 925 solicitations (97,419 clause mentions) we find, without any annotator, that **14.6% of the status-quo entries (8,710 of 59,623) are clauses whose every mention is a checklist item with an empty box**, in 327 of the 388 documents that contain a decided checklist (median 31 per affected document). We then train a small mention-role classifier (0.86 MB, 115 ms per document on CPU, no LLM at inference) and evaluate its document ledgers on a pre-registered, frozen test set of 32 documents against three blind LLM annotators. The model is **not worse than the status quo in F1 (0.912 vs 0.891, difference +0.020, interval [-0.005, +0.046]) and leaves out 38% of non-binding numbers against 4%**, but we cannot claim superiority, two of four pre-registered hypotheses failed, and results depend on who labels referenced requirements. A rules-only baseline is far worse (F1 0.560). We report the evaluation-frame flaw we found and what the next round must change.

## 1. Introduction
A solicitation lists clauses in several ways: incorporated by reference, full text, checklists with marked boxes (52.212-5), narrative citations, and table rows. Regular expressions find clause numbers but not the way each is used. The cost of error is asymmetric and product-specific: a missed binding clause is a compliance risk, a false inclusion is review noise. We treat this as two tasks: (a) role of each mention (ten roles) and (b) the document ledger (which numbers bind).

## 2. Data
Solicitations and attachments from a federal-contracting API (notices from 2024-10, English text layer, 2,027 unique documents; 925 with at least one status-quo entry), the eCFR title 48 history from 2017 for 2,509 sections (version dates, reserved and removed status, the 2025-10-28 RFO model deviation and 47 DoD deviation memos), and layout-aware extraction that keeps checkbox states (glyph, form widget, typed `[X]`, `__ (43)`). Candidate numbers come from regexes validated against the registry; the model never writes a clause number.

## 3. Methods
**Rules.** Section detector and a rules baseline (B1); the status quo (B0) is a port of the production regexes, proven equal to the production PHP on 403 cases. Checkbox item lines are decided by rule (glyph or typed form), validated against 33 agent-labelled cases (33 agree).
**Model.** Logistic regression (one-vs-rest) on 60-odd structural and wording features plus character TF-IDF of the context; temperature scaling (T = 0.525, development ECE 0.06); ledger probability by noisy-OR over mentions with an exclusion factor; binding at q >= 0.5.
**Labels.** No human annotators were available. Mention-level labels: the coding agent read 358 non-checkbox contexts (UNCLEAR excluded); checkbox items are labelled by rule (2,305). Ledger-level gold: the agent, gpt-4o-mini and gpt-4.1-mini each label every clause number blind (B binds, N does not, R referenced requirement, U undecidable); the primary gold is the majority of three.

## 4. Evaluation design
Pre-registered before any test document was labelled (commit 70be1b9): frozen 32-document test set (sha256 recorded), primary metric document-level binding-set F1 with a cluster bootstrap over documents, four hypotheses with numeric thresholds, a model frozen by hash before prediction. Development results (25 documents) were used for all choices; they were more favourable than the test results (specificity 0.72 to 0.88 against 0.38).

## 5. Results
**Objective audit (no annotator).** See Abstract: 14.6% of status-quo entries are empty-box clauses. Version currency (pre-RFO notices, eCFR as authority): of 6,612 ledger entries citing a date, 89.6% match the version in force on the posting day, 8.6% cite an older version, 1.8% a newer one; 68% of entries have no attachable date (an extraction limit).
**Mention level.** On 358 non-checkbox mentions (five folds grouped by document, solicitation or department): B1 35% role agreement, a zero-shot LLM at best 50% (gpt-4.1-mini 52%), the classifier 74 to 78%.
**Ledger level, frozen test (679 labelled numbers, 563 binding).** B0 P 0.830 R 0.963 F1 0.891; B1 F1 0.560; all-candidates F1 0.907; model P 0.881 R 0.945 F1 0.912. H1 (model beats B1 by at least 0.10) holds (+0.351 [+0.216, +0.537]). H2 (specificity at least 0.60 at recall at least 0.90) fails (0.379). H3 holds as non-inferiority only. H4 (threshold from development, 85% coverage at 90% accuracy) fails (coverage 0.423 at accuracy 0.913). Against single annotators the difference to B0 is +0.008 to +0.020; when referenced requirements count as applicable it is -0.016 [-0.044, +0.009].

## 6. Limitations (all of these matter)
1. Gold is LLM-annotated, not expert-annotated; the agent that labelled the gold also designed the features. 2. The sampling frame for development and test (8 to 40 distinct numbers per document) favours plain clause lists and excludes the checklist-heavy documents where over-counting occurs; test prevalence of binding numbers is 83% by majority, 96.5% by the agent, so all methods sit near the all-candidates ceiling. 3. 32 test documents, with repeated templates; the effective sample is smaller. 4. Numbers only: alternates, dates and ranges are not part of the gold. 5. The status-quo regexes are a port; the production ledger logic was not read. 6. English text-layer documents only. 7. Annotator disagreement concentrates on narrative citations; we introduced a fourth label (R) after seeing it.

## 7. Discussion
The robust findings are the objective audit, the failure of a rules-only baseline, and the dependence of conclusions on who labels referenced requirements. The classifier's advantage over the status quo is precision at a small cost in recall; whether it is worth it is a product decision that this study cannot make. The next round needs a checklist-heavy frame, expert or product-reviewer gold, and more evidence lines per number.

## Data and code
Repository `fedproc-ledger` (Apache-2.0); derived tables only would be released, subject to the owner's and the company's approval.
