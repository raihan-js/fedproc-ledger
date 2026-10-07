# FedProc-Ledger: integration contract for VETR (draft v0.3, 2026-10-07)

Audience: the VETR team. Status: **proposal; nothing is deployed, nothing in the VETR repository was changed** (read-only
access; `FarClauseDetectionService.php`, `FarClauseController.php`, `ImportRfpFromUrl.php`, `AiProviderFactory.php` and
`infrastructure/aws/cloudformation.yml` read 2026-10-07). Numbers below are from this repository's results
files; where a number is a development result, it says so. Public artefacts: model
`https://huggingface.co/raihan-js/fedproc-ledger-v1`, data
`https://huggingface.co/datasets/raihan-js/fedproc-ledger-bench`.

## 1. What it does, and what it must not be used for
Input: one solicitation document (PDF or DOCX) or its extracted text. Output: a **clause ledger**: for every FAR/DFARS
clause number found, whether the document *binds* the contract to it (incorporated by reference, full text included, or a
selected checklist item), a probability, and the evidence lines. It also decides checklist boxes (`⟦X⟧`, `⟦ ⟧`, `__ (43)`,
`X (44)`) by rule, which is objective.
Not for: legal advice; deciding obligations without a person; documents without a text layer (about 3% are scanned: the
extractor flags them, no ledger is produced); clause ranges ("52.219-1 through 52.219-4") and alternates' dates are not
resolved in this version.

## 2. Evidence for its usefulness (read D-023 to D-036 before deciding; every number is in results/*.json)
- **Objective, annotator-free:** in 6,472 documents, 13.5% of the entries the VETR-style regexes would list (57,225 of 423,328) are clause
  numbers whose every mention is a checklist item with an **empty** box; in checklist-heavy documents 25.4% (round 2) and 31.0% (round 3).
  The checkbox rule agreed with a reader on 100 of 100 random items (40 + 60). Lower bound; describes the ported regexes, not VETR's current logic.
- **Round 4, the first fresh pre-registered test of the shipped rules v1.2 (D-037; 26 new documents, 557 numbers, majority of the coding agent
  and two LLM judges, no human experts):** F1 0.921 against 0.780 for the status-quo regexes (+0.142 [+0.085, +0.210], positive for all three
  annotators), specificity 76% against 10%, recall 0.940 against 0.877. Gains are large in checklist-heavy documents (+0.33 F1) and small in short
  documents without checklists (+0.03). Round 3 (rules v1.1, D-035) gave +0.111 with recall 0.874 against 0.933: the recall cost was removed by v1.2.
- **Earlier rounds:** round 1 (D-028, D-031): non-inferior, +0.020 original and +0.023 after a post-hoc protocol correction; round 2 (D-032, D-033):
  the pre-registered non-inferiority test FAILED (-0.103) because the LLM judges accepted unchecked boxes as binding; with corrected instructions
  +0.047. Annotator dependence is the main uncertainty: **the product gold sample in section 5 is required before any customer-visible use.**
- **Round 5 (a second fresh test, D-039; 24 documents, 420 numbers):** +0.097 [+0.040, +0.158] F1 over the status quo with the stacker, positive for all three annotators, specificity 78% against 19%, recall 0.926; the stacker was no better than the simpler max-over-mentions rule (+0.004), which stays the default (`FL_STACKER=1` enables the optional stacker). Corpus-wide, 13.8% of the status-quo entries are empty-box clauses (rules v1.2).
- **Round 6 (fresh, rules v1.3, D-041; 24 documents, 490 numbers): all six pre-registered hypotheses hold:** +0.107 [+0.057, +0.161] F1 over the status quo (interval above zero for every annotator), specificity 73% against 8%, recall 0.939.
- **Round 7 (fresh, rules v1.4 on the temporal hold-out, D-044; 27 documents posted after the last acquisition day, 515 numbers): all six pre-registered hypotheses hold:** +0.084 [+0.028, +0.143] F1 over the status quo, positive on all three single annotators, specificity 70% vs 14%, recall 0.903 vs 0.939. Fourth fresh round in a row (effects +0.14, +0.10, +0.11, +0.08).
- **Weak LLM labels did not help (D-034).** The review-queue target (q between 0.1 and 0.9 holds at least 60% of the errors) failed in rounds 4 (58%) and 5 (48%).
- **Recommendation:** adopt the checkbox rule first (zero-risk, objective). Use the model for *ranking and flagging*, not for silently removing
  clauses: show every number with its tier and probability; route UNDETERMINED and low-margin entries to a person (on round 4, the queue of numbers with q between 0.1 and 0.9
  is 32% of the labelled numbers and holds 58% of the majority-gold errors; on round 5, 17% and 48%).

## 3. Interface (sidecar service; the model never runs inside PHP)
`POST /v1/ledger` with `{"document": <bytes or text_layout pages>, "posted_date": "YYYY-MM-DD"}` returns:
```json
{
  "contract_version": "0.3",
  "model": {"name": "role_model", "sha256": "…", "rules_version": "1.4", "aggregation": "max over mentions"},
  "document": {"pages": 12, "scanned": false, "extraction_warnings": [], "candidates": 119},
  "entries": [
    {
      "number": "52.204-21", "alternate": null, "cited_date": "2021-11",
      "tier": "BINDING | NOT_BINDING | UNDETERMINED",
      "q": 0.97,
      "decided_by": "model | box_rule | para_a_rule | text_rule",
      "registry": {"status": "active|reserved|removed|rfo_only|unknown", "cited_date": "2021-11", "version_in_force": "2021-11",
                   "currency": "matches|older|newer|no_date_cited|no_version_data|rfo_era_not_judged|unknown_posted_date"},
      "evidence": [{"page": 3, "line": 41, "role": "INCORPORATED_BY_REFERENCE", "p": 0.95, "source": "model", "text": "…"}]
    }
  ],
  "summary": {"binding": 41, "not_binding": 22, "undetermined": 6, "rule_decided_share": 0.61}
}
```
Rules: `q` is the **maximum** over mentions of the binding probability (calibrated by temperature scaling; development ECE 0.06; v0.1 used noisy-OR);
`tier` = BINDING if `q >= 0.7`, NOT_BINDING if `q <= 0.3`, otherwise UNDETERMINED (a person decides); the thresholds are
configuration, not constants. Box-rule entries have `q` 1.0 or 0.0. The model **never creates a clause number**: numbers come from
regex candidates validated against the eCFR registry.

Version currency is filled when the posting day is given (`--posted-date YYYY-MM-DD`, or the form field `posted_date`): the cited date against the eCFR version in force that
day; notices posted on or after 2025-10-28 (RFO era) are not judged because agencies adopt the deviation at different times.

Run it: `fl ledger FILE.pdf [--out ledger.json]` (about 2.5 s for a 42-page PDF) or `fl serve` then `curl -F file=@FILE.pdf localhost:8077/v1/ledger`
(`serve/ledger.py`, `serve/app.py`; tests in `tests/test_ledger_service.py`). Scanned documents return `scanned: true` and no entries.

## 4. Operating numbers (measured here, CPU only)
Model file 0.46 MB (public numpy archive; the 0.86 MB sklearn pickle stays in the research repo); 115 ms per document including parsing and feature building (12-core desktop, 60 documents, 6,038 mentions);
extraction with PyMuPDF is separate (seconds for a long PDF). No GPU, no LLM, no network at inference. Reproduce: `fl model train`,
`fl model predict`, `scripts/ledger_eval.py`.

## 5. Where it plugs into VETR (mapped to the current code, read-only 2026-10-07)
- **New job** after `app/Jobs/ParseRfpDocument.php` succeeds (it is dispatched with `($rfp, $document)` from `app/Jobs/ImportRfpFromUrl.php`): `BuildClauseLedger` sends the stored document bytes to the sidecar and stores the result in new tables (`rfp_clause_ledgers`, `rfp_clause_entries`), behind a per-organization feature flag. No change to the parse job itself.
- `app/Services/FarClauseDetectionService.php::detectFromText()`: when a ledger exists for the RFP, use ledger entries (binding only) for `matched`, expose `not_binding` separately, and keep regex as the fallback when the sidecar is down or the flag is off. The parity port (`tests/test_vetr_parity.py`, 403 cases) pins the fallback behavior.
- `app/Http/Controllers/FarClauseController.php::solicitationContext()` (which today hard-codes `is_commercial` to `null`): set `is_commercial` from `derived_facts.is_commercial` only when present with evidence; otherwise keep `null`. `proposalCompliance()` then resolves Part-12 verdicts instead of returning UNDETERMINED.
- The far-compliance page: show status, cited date, date status and the evidence snippet per clause; separate "Provisions (answer in your offer)" from "Clauses (comply after award)".
- Infrastructure (`infrastructure/aws/cloudformation.yml`, GovCloud us-gov-west-1, ECS Fargate): a separate service in the existing VPC, sized from the CPU numbers above (the current worker task at 0.25 vCPU / 512 MB is too small to host extraction + inference; start at 1 vCPU / 2 GB and measure). The sidecar needs no GPU, no model downloads at boot if baked into the image, and no outbound network.

## 6. Compliance boundary (Bedrock-only deployments)
VETR pins every org to in-boundary Amazon Bedrock when `ai.bedrock_only` is set or the org is a government agency (`AiProviderFactory::bedrockOnly`). The ledger sidecar is **not an LLM call and needs no exception**: it is deterministic CPU code (regex + logistic regression + rules) that runs inside the VPC, makes no outbound request, stores no document text and logs no document content. Customer documents stay in-boundary by construction; reviewer PII never leaves either (extraction redacts contact patterns before anything is stored). The Bedrock boundary question therefore does not arise; note this explicitly in the deployment review so nobody wires the ledger through an LLM provider.

## 7. What VETR must provide / decide
1. A **gold sample from the product**: 200 documents with the ledger the VETR reviewers accept. This repository's gold is LLM-annotated
   and sampled from a frame that under-represents checklist-heavy documents; product acceptance should rest on VETR's own data.
2. The policy question in D-024: should a narrative requirement ("in accordance with FAR 52.204-7, registration is required") appear in the
   ledger? The model separates INCORPORATED/FULL_TEXT/SELECTED from NARRATIVE/INTERNAL; the product decides how to show the second group.
3. Cost of a false inclusion versus a miss (it sets the `tier` thresholds; development: q >= 0.7 gives precision 0.96 at recall 0.84 on the majority dev gold).

## 8. Acceptance tests before any production use
a. Parity: the ported regexes reproduce the VETR PHP outputs on 403 cases (`tests/test_vetr_parity.py`); re-run on VETR's current service.
b. On VETR's gold sample (about 200 documents with the ledger the reviewers accept): ledger precision, recall and F1 with a cluster bootstrap over documents; the model must be non-inferior to the current
   ledger on F1 and recall (margin to be set by VETR) before it affects any customer-visible output. Research rounds 4-7 (+0.08 to +0.14 F1, LLM gold) do **not** substitute for this.
c. Shadow mode for four weeks: log differences (entries only the model includes or excludes), review a weekly sample.
d. Drift monitors: share of box-rule decisions, mean `q`, share UNDETERMINED, share of documents with `scanned` true; alert on a shift above 10 points.
e. Testability now: `fl ledger FILE.pdf` and `fl serve` run locally against the same contract (tests in `tests/test_ledger_service.py`); point a staging worker at the sidecar URL and compare with detection output before any flag is enabled.

## 9. Data, privacy, licence
Solicitation documents are public SAM.gov attachments; the extractor redacts personal data patterns (emails, phones, hardened against glued tokens in D-045; the public release verifies zero remaining) before any text is
stored for training or release (`extract/privacy.py`). Training excerpts stay inside this repository's `data/` (git-ignored). The public release (model `raihan-js/fedproc-ledger-v1`, data `raihan-js/fedproc-ledger-bench`, authorized by the CTO 2026-10-07) contains derived tables and short snippets only, never customer documents; the sidecar stores nothing and logs no document text.

## 10. Versioning
`contract_version` changes when fields change; `model.sha256` identifies the weights; the registry snapshot date is recorded in
`data/processed/manifest_registry.json`. A new RFO deviation date or a new agency checklist format means re-running `fl registry build`
and, if the box forms change, extending `label/pilot.py: typed_item_state` (its tests list the supported forms).
