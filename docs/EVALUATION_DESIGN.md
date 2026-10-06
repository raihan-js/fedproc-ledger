# Evaluation design: scores, confidence, thresholds, and the improvement loop

Status: **proposal for the pre-registration** (plan section 10.4). Nothing here is tuned on test data. The formulas are implemented
and unit-tested in `src/fedproc_ledger/eval/metrics.py` (pure functions, no model needed), so they can be applied to B0, B1 and any
future model the same way. Numbers produced before human gold labels exist are **not results**.

## 0. What can and cannot be evaluated today

Evaluation needs human gold labels; training needs labels too (gold plus silver). So the order is: pilot annotation (the owner, with
B1 pre-labels to make it fast) -> first honest numbers for B0 and B1 -> silver labels -> first trained model -> iteration. Until the
pilot, everything printed about B0/B1 (for example "B1 binds 19,742 entries where B0 binds 51,902") is a signal, not a score.

## 1. Units and the primary score

- **Mention** = one candidate (a clause number at a place in a document) with one of 9 roles (plus UNCLEAR, excluded from scoring).
- **Ledger entry** = (number, alternate) that binds the document. Binding roles B = {IBR, FULL_TEXT, CHECKLIST_SELECTED}; an
  EXPLICITLY_EXCLUDED mention of the number removes it.
- **Primary metric (pre-registered in the plan): document-level binding-set F1, micro over documents.** For document d, predicted
  set P_d and gold set G_d: TP = |P_d ∩ G_d|, FP = |P_d \ G_d|, FN = |G_d \ P_d|; precision, recall and F1 from the sums over
  documents. A **strict** variant matches (number, alternate, cited_date).
- Secondary: mention-level macro-F1 and per-role F1, binary binding-vs-not accuracy, whole-ledger exact match, candidate recall,
  F2 (recall-weighted: a missed obligation costs more than an extra one), version-currency categories.
- Intervals: **cluster bootstrap over documents**, 10,000 resamples; model-vs-baseline differences by **paired** bootstrap on the
  same resamples. Mentions inside one document are correlated, so mentions are never resampled independently.

## 2. Confidence: from a model score to a ledger verdict

1. The classifier gives logits for each mention. **Temperature scaling** fits one T on dev by minimising NLL; p_m = softmax(z_m / T).
2. Mention binding probability: b_m = sum of p_m(r) over r in B. Exclusion probability: e_m = p_m(EXPLICITLY_EXCLUDED).
3. Ledger entry probability (noisy-OR over the mentions of the entry, then multiplied by "not excluded"):

       q(n, a) = [ 1 - prod over mentions m of (n, a) of (1 - b_m) ] * prod over mentions m of n of (1 - e_m)

   Alternative: `max` instead of noisy-OR (mentions of one clause are correlated, so noisy-OR can overstate). Both are computed and
   the one with the lower dev log-loss is used; the choice is fixed before test.
4. **Verdict with an abstain band** (plan 15.1, "low confidence never becomes a verdict"): binding = true if q >= t, false if
   q <= 1 - t, otherwise **null** (not determined, listed in warnings). t >= 0.5.
5. **Choosing t on dev only:** the smallest t such that verdict accuracy (on the entries that get a verdict) reaches the target
   precision (default 0.98), which maximises coverage under that target. Reported with its coverage: for example "98% verdict accuracy
   on 91% of entries, 9% sent to a person".
6. **Calibration and risk-coverage diagnostics:** ECE (10 equal-mass bins), Brier score, log-loss, and the **risk-coverage curve**
   (entries sorted by confidence max(q, 1-q); error rate among the most confident k). **AURC** is the mean error over coverage; lower
   is better. These tell whether the confidence is usable, independently of the F1 at one threshold.

## 3. Model-selection score (dev only)

No arbitrary weighted sum. Candidates are ranked **lexicographically**: (1) dev binding-set F1 from grouped cross-validation;
(2) ECE; (3) coverage at the 98%-precision target; (4) CPU latency. A change counts as an improvement only if the paired-bootstrap
interval of the F1 difference excludes zero or the change is free (same cost, simpler). Every look at dev is logged in
`results/leaderboard.jsonl` with the config hash and a counter, so adaptive overfitting is visible.

## 4. Experiment protocol (the Kaggle loop, with the guard rails research needs)

- **Grouped K-fold (K = 5) by solicitation** over gold_train plus dev (70 documents) for fast iteration; out-of-fold predictions are
  stored, so every comparison is on identical documents. Repeat with 3 seeds. The test splits stay sealed until `fl evaluate --final`.
- Each iteration: change one thing, run, add a leaderboard row, read the **top error categories** (plan 13.5: lost checkbox, section
  boundary, cross-reference versus incorporation, exclusion missed, alternate/date, extraction artefact, ambiguity), fix the largest
  category with data or a rule, repeat. The error taxonomy decides the next experiment, not intuition.
- Ablations are pre-planned (plan 12.3), not discovered after the fact.

## 5. Levers, in the order I expect them to pay off

1. **Label efficiency:** B1 pre-labels in the annotation tool, bulk apply per section, active learning (annotate the documents where
   B1 and the model disagree or are least confident). The gold set is the bottleneck, not GPU time.
2. **Context engineering (input construction):** layout markers, section tags and registry facts (kind, status, RFO status, cited
   date) written into the input; a candidate-marked span plus a line window; neighbouring list lines; document-level features
   (form type, RFO era, commercial indicators).
3. **Rules as features (stacking):** B1's role, reason, section and box state fed to the head, so the model learns where B1 is wrong
   instead of relearning what it already gets right.
4. **Structured decoding and constraints:** registry kind and status as hard checks, section-state transitions over lines (a CRF or a
   small sequence layer over line representations), whole-ledger consistency (an exclusion overrides, a range counts once).
5. **Synthetic data with exact labels:** a generator that renders documents from the registry with controlled structures (IBR lists,
   52.212-5 style checklists with random boxes, full-text clauses, tables of contents, exclusions, cross-references, RFO variants,
   scanned-like noise). Pretrains layout and role behaviour with perfect labels; validated only on real gold because of the
   distribution gap.
6. **Silver labels and distillation:** a stronger open-weight teacher (local Qwen through Ollama, or larger open-weight models on the
   owner's NVIDIA API) labels candidate chunks as JSON; keep labels where teacher and B1 agree or the teacher is confident; train the
   small student (ModernBERT-base, 149M, CPU-friendly; later int8 ONNX or a smaller student) with confidence-weighted loss; iterate
   with self-training. The teacher is a labeler, never a judge of results.
7. **Training recipe:** multi-task heads (role, section, date/alternate), class-weighted or focal loss, label smoothing, layer-wise
   learning-rate decay, EMA/SWA, seed ensembles, hard-example mining from the OOF errors.
8. **Calibration and abstention** as in section 2: a small model that knows when to abstain is more useful in the product than a larger
   one that guesses.

## 6. Honest expectations

First trained numbers come after silver labels exist (days, once the pilot is annotated); a good model takes weeks of the loop above.
The pilot's go/no-go (plan 9.5) decides whether a model is the main contribution or the rules engine and the corpus findings are.
With 150 gold documents, intervals are wide; the claims will be sized to the intervals.
