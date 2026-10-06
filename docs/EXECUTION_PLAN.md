# Execution plan: how the agent runs `docs/PLAN.md`

`docs/PLAN.md` (the spec) says **what** to build. This file says **how I execute it**: the order, the exact steps, what is automatic, where I stop, and what I need from Raihan and when. Written 2026-10-06, after Phase 0. Facts about external APIs are in `docs/decisions.md` (D-005, D-006).

## 0. Operating protocol

**Autonomy levels.**
- **Green, just do it:** code, tests, refactors, local runs, fetching public docs and eCFR, reading VETR code (read-only), writing docs, local git commits, deleting my own scratch/cache files.
- **Amber, do it, then show it at the checkpoint:** choosing thresholds on dev, picking heuristics, anything that changes a number you will see.
- **Red, stop and ask first:** spending over $5 in one run (silver labels, API baselines, rented GPUs); deleting anything in `data/raw/`; adding a dependency not already in `pyproject.toml`; any push to GitHub or Hugging Face; creating a repo; changing the label schema after annotation starts; sending anything outside this machine other than GovCon / eCFR / agency page reads; anything touching the VETR repo or production.

**Resume protocol (the power-loss lesson).** `docs/STATE.md` is updated after every step. Every step is resumable: it reads its manifest, skips outputs whose hash matches, and appends rather than overwrites. Long jobs run detached (`nohup`), log to `data/logs/<step>.log`, and a watcher reports server/API loss, repeated errors and exit. After any interruption I check log, statuses and manifest before trusting a result; connection or timeout failures are infrastructure and are re-run, never counted as results.

**Number discipline.** A number appears in a README, card, paper or article only if it is in `results/*.json` written by code here. `fl report` generates every table. I recompute before quoting. Wording follows `../noeon-prep/content/interview/09-never-say.md` and `10-profile-fixes.md` (read before any public text).

**Verification before "done".** A step is finished when: its tests pass (`uv run pytest`, `ruff`, `mypy`), a smoke run on real data works, its manifest is written, `docs/STATE.md` and `docs/decisions.md` are updated, and it is committed locally. No claim of success without the command output.

**Evaluation honesty.** No language model scores any result: silver labels and LLM baselines are *predictions* scored against human gold. Test splits are read only by `fl evaluate --final`, once, after the pre-registration commit.

## 1. Phase map

| Phase | What | Agent time | Raihan's time | Gate |
|---|---|---|---|---|
| 0 | Scaffold, env, CLI, CI | done | review | **Checkpoint 0** |
| 1 | GovCon acquisition (about 3,000 solicitations) | 2 days, mostly unattended | key, plan, budget OK | **Checkpoint 1** |
| 2 | eCFR registry, version history, deviations | 1.5 days | review | **Checkpoint 2** |
| 3 | Layout-aware extraction, checkbox markers, legal filter | 3 days | review HTML report | **Checkpoint 3** |
| 4 | Candidates, sections, B0, B1 | 2 days | eyeball 5 docs | **Checkpoint 4** |
| 5 | Schema, guidelines, annotation tool, **pilot, go/no-go** | 3 days | about 8 h annotating, decision | **Checkpoint 5 (decision)** |
| 6 | Gold annotation, splits, IAA, pre-registration, freeze | 1 day tooling | 35 to 45 h annotating, Dr. Smith's 30 docs | **Checkpoint 6** |
| 7 | Silver labels | 2 days | spend OK | none (cost gate) |
| 8 | Model, ablations, baselines, export | 5 days, multi-day GPU | spend OK for B2 | none |
| 9 | Evaluation, currency, downstream, corpus findings, error analysis | 4 days | claims review | **Checkpoint 9** |
| 10 | Paper, cards, article, releases | 1 to 2 weeks | permission, pushes | pushes need OK |
| 11 | `docs/INTEGRATION.md`, local `fl serve` | 2 days | review | Deployment is a separate instruction |

## 2. Steps per phase

### Phase 0: scaffold (done; remaining to close the checkpoint)
Done: repo, `uv` env (Python 3.11.15, torch 2.14.1+cu130), `fl` CLI shape (every step exists as a placeholder, `fl env` and `fl phases` work), `manifest.py` (inputs, outputs, git SHA, config hash, timestamp), `config.py` (TOML), 9 tests, ruff and mypy clean, CI workflow, pre-commit config, `CLAUDE.md`, `docs/PLAN.md`, `docs/decisions.md`, `docs/preregistration.md` template, `docs/STATE.md`.
Left: first local commit; `pre-commit install`. **Checkpoint 0:** tree, `fl --help`, GPU line, passing tests (all shown in the chat).

### Phase 1: acquisition
1. `acquire/ratelimit.py`: token bucket (tests with a fake clock). `acquire/budget.py`: a Python port of the design of VETR's `GovConCallBudget` (local decrement, reserve, hard ceiling, **unknown quota stops**, refresh from the vendor figure every N calls). Every call appended to `data/logs/api_calls.jsonl`.
2. `acquire/govcon.py`: `httpx` client with Bearer auth, `tenacity` backoff on 429/5xx, `MockTransport` tests for pagination, 402 (free-trial limit, `content=` on non-Pro), 429, `total_is_estimate`. The key is read from `.env` only and never logged (a test asserts it never appears in a log line).
3. `fl acquire probe`: one `limit=1` call; prints plan facts (window, page limit, quota) without the key. Writes them to `docs/decisions.md`.
4. Search month by month from 2024-01 to the last full month, `Solicitation` and `Combined Synopsis/Solicitation`, `has_attachments=true`, `limit` at the plan maximum. If a month reports `total_is_estimate`, split it by week, then by agency. Raw pages saved under `data/raw/search/` (resume-safe).
5. Build the notice pool: dedupe on `solicitation_number` keeping the latest `notice_id` (others into `notice_lineage`), department mapping (table plus tests), stratified sampling with the 25% cap, `description_text` kept as a pseudo-document. **Personal contact fields (`contact_*`, `secondary_contact_*`) are dropped from `notices.parquet`**; they are never needed.
6. Attachments call per kept notice, then download: `httpx`, GET with up to 5 redirects, `User-Agent` from `configs/acquisition.toml`, at most 1 file per second, backoff, sha256 de-duplication, keep `.pdf/.docx/.doc/.txt`, skip over 50 MB, record skipped files. Bytes to `data/raw/files/{sha256}.{ext}`.
7. Tables `notices.parquet`, `documents.parquet` (columns as in plan 5.5), `results/acquisition_stats.json`, manifest.
8. The legal and privacy filter (plan 5.4) needs document text, so its marking detection runs in Phase 3 and writes `license_flag`; Phase 1 only stores the raw bytes.

Arithmetic to expect (verify at the probe): about 33 monthly windows; roughly 3,000 to 6,000 attachment-list calls (one per notice) at about 1,000 requests per hour is 3 to 6 hours of API time; about 12,000 files at 1 per second is about 3.5 hours of download time; 10 to 40 GB. Everything runs unattended in the background with a watcher.
**Checkpoint 1:** `acquisition_stats.json` and 10 random documents (title, agency, size); disk use confirmed.
**Needs:** `GOVCON_API_KEY` in `.env`, the plan tier, the key decision in D-009, the disk and call budget OK.

### Phase 2: registry from eCFR
1. `registry/ecfr.py`: client (research `User-Agent`, compression allowed, polite rate, cache every response under `data/raw/ecfr/` by endpoint, section and date).
2. Enumerate Title 48 from `structure/{date}/title-48.json` (latest date from `titles.json`): every section in the x52 parts (FAR 52, DFARS 252, and each agency supplement present: GSAM 552, VAAR 852, HSAR 3052, NFS 1852, DOSAR 652, AIDAR 752, DEAR 952, HHSAR 352, AGAR 452, AFARS 5152, DAFFARS 5352, NMCARS 5252, HUDAR 2452); everything else is recorded as `not_in_ecfr`.
3. Parse each section (stdlib XML): number, heading, clause date from the heading line, alternates, `prescribed_in`, and `kind` from the prescription wording ("insert the following provision/clause"); unparseable is `unknown`, never guessed.
4. Versions: `versions/title-48.json?section=...` for each section; fetch the section at each change date and store `{effective_from, effective_to, clause_date, alternates}`. Expect thousands of cached requests; throttled, resumable.
5. `registry/dates.py`: normalise `(OCT 2022)`, `Oct 2022`, `OCT 2022`, `10/2022`, `October 2022` to `YYYY-MM` (tests from real snippets).
6. Deviations table: scrape the three starting URLs plus agency pages found there, by hand-written parsers with the URL and fetch date per row; if a page cannot be parsed reliably, record the URL and ask. Used only to label citations, never to change a ledger.
7. Tests from plan 6.4 (30 known numbers resolve; `kind` correct for 20 hand-checked numbers; 52.219-14 has several clause dates since 2017). Cross-check against the earlier FedProc-Constrained registry (1,056 canonical IDs) as a sanity test; differences are logged, not hidden.
**Checkpoint 2:** counts per regulation, `kind` distribution, unknowns, 10 sampled rows with eCFR URLs.

### Phase 3: layout-aware extraction
1. `extract/pdf.py`: per page `text_plain` and `text_layout` (PyMuPDF). Four checkbox sources, each recorded when it fires: form widgets, glyphs (log every code point met, add each to the tests), vector drawings (square candidates, confidence), and `lost` (a checklist-looking line with no signal gets `⟦?⟧`).
2. `extract/docx.py`: content-control and legacy form checkboxes, symbol runs; `.doc` through LibreOffice headless (installed on this machine); scanned PDFs flagged `scanned=true` and excluded.
3. Offset map from every character of `text_layout` to page, bounding box and `text_plain`.
4. Run the **legal and privacy filter** here: marking detection (`CUI`, `FOUO`, `Proprietary`, `Source Selection Information`, distribution statements, export control), `license_flag`, and a tested redaction of emails and phone numbers for any released text.
5. Test corpus: I hand-inspect about 20 pages covering each signal type and store only the small snippets as fixtures. The extractor's recovery on them is reported at Checkpoint 3 (this is the seed of Finding F2; the real measurement is on gold).
6. `data/processed/pages.parquet` and an HTML report (page image beside `text_layout`, markers highlighted).
**Checkpoint 3:** the HTML for 5 checklist pages and the counts per box source over the pool.

### Phase 4: candidates and baselines
1. `candidates/patterns.py`: port the 16 regex entries of VETR's detection service. **Parity test:** a small PHP script (PHP 8.3 is installed; VETR's `vendor/` is present) runs VETR's service on fixture texts and writes JSON; the Python port must match it before any extension is added. The PHP script lives in `scripts/php/`, takes `VETR_PATH` from the environment and never modifies VETR.
2. Extensions from plan 8.1 (hyphen variants, stray spaces, prefixes, subparagraphs, ranges, non-clauses still emitted) with a test per rule; candidate fields as specified; `in_registry` from Phase 2.
3. Section detector (state machine over headings) and rules baseline B1 (as strong as I can make it, tuned only on pilot-free dev material), plus B0 (the VETR status quo).
4. Candidate recall is measured later on gold; here I report counts per pool document.
**Checkpoint 4:** B1 output on 5 documents as an HTML table.

### Phase 5: schema, guidelines, tool, pilot
1. Fetch the current text of 52.212-5, 52.212-4, 52.252-2 and any RFO changes from eCFR and agency pages (URL and date recorded) and write `docs/annotation_guidelines.md` from them, with 2 to 3 real examples per role, edge cases and a decision tree.
2. Streamlit annotation tool (`fl annotate`) as in plan 9.4 (keyboard shortcuts, bulk apply with logging, computed ledger with override, time per document, save after every action).
3. Pilot document selection (20: about 8 checklist, 6 IBR, 6 other), stratified and recorded. Raihan annotates.
4. `fl pilot`: B0 binding-set precision/recall, B1 mention macro-F1 and binding-set F1, share of non-binding mentions, checkbox recovery by source, minutes per document. Go if B0 precision is under 0.85 or B1 binding-set F1 is under 0.90; otherwise pivot (plan 9.5).
**Checkpoint 5 (decision):** pilot report, `results/pilot.json`, the time estimate for the full gold set, a recommendation. I stop and wait.
**Needs:** about 8 hours of Raihan's time in a block; Dr. Smith's review of the guidelines.

### Phase 6: gold, splits, pre-registration
1. Gold annotation to 150 documents (the pilot counts if the guidelines did not change). I prepare batches and track progress and agreement drift.
2. Splits by `solicitation_number` group (45/25/50/15/15); **the two out-of-distribution departments are chosen and recorded before any modelling**; `test_recent` is the last 3 months.
3. IAA: a second annotator labels 30 documents; Cohen's kappa on role and Jaccard on binding sets; below 0.75 revise the guidelines and re-annotate the affected cases.
4. Fill `docs/preregistration.md` (hypotheses with numeric thresholds, tests, baselines), commit it, record the hash; hash every split file; test files are then read only by `fl evaluate --final`.
**Checkpoint 6:** IAA report, split sizes, frozen hashes, the pre-registration commit.

### Phase 7: silver labels (cost gate)
Rules (B1) on every clause-bearing pool document outside dev/test solicitations; an LLM labeler (model pinned in config, temperature 0, JSON validated against the schema) on chunks with candidates listed by id; keep agreement, send disagreements to a second pass or drop; agreement per role; silver accuracy measured against gold dev. **Ask before running**: a dry run first prints the number of chunks, tokens and estimated cost; I proceed only with Raihan's OK (the plan expects $20 to 60; zero-cost alternative: a local Qwen2.5-7B-Instruct through vLLM).

### Phase 8: the model
1. `data/` builder: windows of W tokens with stride W/2, markers added as new special tokens, candidate-to-window assignment, **9 trainable roles** (see section 3, item 2).
2. `model/`: ModernBERT-base encoder, candidate head (candidate span mean plus line mean, 2-layer MLP), optional auxiliary section head, class-weighted cross-entropy with label smoothing; MLflow logging with config hash, data hashes and git SHA.
3. Throughput benchmark first (tokens per second at W of 1,024, 2,048, 4,096 on the 3060 with bf16 and SDPA), then a written time estimate for the whole grid before launching it.
4. Training: stage A on silver, stage B on `gold_train`, 3 seeds per configuration, early stopping on dev binding-set F1. Ablations A1 to A7 and baselines B2 (spend gate) and B3 (DeBERTa-v3-base, window 512) on the same candidates. A4 uses the v0 `model.pt` state-dict mapping (D-007).
5. Export: ONNX plus int8, parity (at least 99% role agreement, at most 0.5 points binding-set F1 difference), CPU latency p50 and p95 on 2 and 4 threads, peak RAM.
Planning figure: about 14 configurations times 3 seeds is about 42 runs; the benchmark in step 3 turns that into hours before anything long starts.

### Phase 9: evaluation and findings
`fl evaluate` on dev during development; `fl evaluate --final` once per split. Cluster bootstrap over documents (10,000 resamples) for every interval, paired bootstrap for model versus baseline. `fl currency` (eCFR version in force on `posted_date`; categories as in plan 13.2; the word "mismatch", not "error"). Applicability port (`eval/applicability.py`) with a PHP parity test on 200 fixtures against VETR's own class (read-only, run locally). Corpus findings F1 to F5, each with the model's error rate on gold for that quantity. Hand-review 100 test errors by category.
**Checkpoint 9:** `results/final/*.json`, generated tables and figures, error analysis, a one-page statement of what the results support. **Raihan approves the claims before any writing.**

### Phase 10: paper, cards, article, releases
Literature search with every citation found first on arXiv, ACL Anthology or Semantic Scholar and saved in `paper/refs.bib`; paper in ACL LaTeX; dataset and model cards; README; dev.to and Zenn drafts. **Pushes (GitHub, Hugging Face, arXiv) only with Raihan's OK**, and only after the written permission from Acu-Elligent LLC (plan 14.2). Public text follows the claims rules in `../noeon-prep`.

### Phase 11: integration contract
`docs/INTEGRATION.md` and a local `fl serve` that returns the schema in plan 15.1 (CPU, ONNX int8, receives original bytes, low confidence becomes `null`, never a verdict), with a contract test for the response schema. No edits to VETR; deployment to GovCloud is a separate instruction.

## 3. Issues found in the spec (to resolve or confirm)

1. **v0 weights are `model.pt`, not safetensors** (D-007): A4 needs a state-dict key mapping; v0 used 512-token windows.
2. **Role count:** plan 9.1 lists 10 roles including `UNCLEAR`; 12.1 says the head predicts 10 and also that `UNCLEAR` is not a training target. I will use a **9-class head** and count `UNCLEAR` separately.
3. **GovCon free trial** (100 results per page, a 90-day window) cannot reach 2024-01; a paid plan is needed, and `content=` needs Pro (D-005).
4. **The legal filter needs text**, so marking detection runs in Phase 3, not at download.
5. **Personal data in the search payload** (`contact_*`): dropped from the stored notices (D-005).
6. **Shared production quota** if the same GovCon key is used (D-009).
7. **eCFR documentation is bot-gated**; API shapes were verified by probing (D-006), and `full/` needs a compression header.
8. **Annotation workload is uncertain** until the pilot reports minutes per document; 150 documents of about 60 checklist items each could exceed the 35 to 45 hours planned. Fallback: fewer, longer-checklist documents, or a smaller `test_ood_agency` and `test_recent`, decided at Checkpoint 5.
9. **Python 3.11** came from `uv` because the system Python is 3.12 (D-002).
10. **Baseline model IDs** (B2) are pinned at run time to the current models; costs are estimated by a dry run first.
11. **A 12 GB GPU** limits ModernBERT-large to window 1,024 to 2,048 with gradient checkpointing and batch 1; I will say so in A5 rather than extrapolate.
12. **Conflict of interest and permission:** the work uses VETR context and Dr. Lori Smith is both VETR's founder and the proposed domain validator; the paper needs a conflict-of-interest statement and written company permission.

## 4. What I need from Raihan

**Now (to start Phase 1):**
1. **`GOVCON_API_KEY`**: copy `.env.example` to `.env` in `fedproc-ledger/` and paste the key there yourself (it never has to pass through the chat). **Which plan** it is (free trial, Developer, Pro). **A separate key from the production one**, if you can get one (D-009); otherwise tell me the reserve to protect for VETR (for example "stop while 2,000 calls/hour-equivalent remain") and which hours to avoid.
2. **OK for disk use** of up to about 40 GB under `fedproc-ledger/data/` (197 GB free now).
3. **OK for the location and name** (`research-learn/fedproc-ledger`, GitHub `raihan-js/fedproc-ledger` later) and for the optional extras and `mlflow`/`fastapi` listed in D-004.
4. **Confirm VETR read-only access** at `/home/raihan/Desktop/APPS/VETR-Framework` for the port and the PHP parity scripts.

**Soon (week 2):** a block of about 8 hours for the 20-document pilot; whether Dr. Lori Smith can review the guidelines and second-annotate 30 documents (I need her yes or no early because it sets the schedule).

**Later, but with lead time (please start these now):** the rejection reason from arXiv and a possible cs.CL endorser; written permission from Acu-Elligent LLC to publish the paper, model and dataset (and the affiliation line); an Anthropic API key and a spending OK for Phase 7 and the B2 baselines (the plan expects $20 to 60 and under $40); someone fluent to check the Japanese summary. The Hugging Face token is already on this machine; I will not push anything without your OK.

## 5. Resource plan

- **Disk:** data 10 to 40 GB, venv 6 GB, models a few GB; `/home` has 197 GB free. Raw data and gold labels are the irreplaceable parts: gold labels are backed up to the private `raihan-js/research-archive` dataset after every annotation session (with your OK), and `data/raw/` is never cleared by the workspace clearing script (it is not tracked in git; the project will be excluded from it until the release).
- **GPU:** RTX 3060 12 GB, local Linux, so vLLM works natively for the local baseline. Nothing needs a rented GPU unless the throughput benchmark in Phase 8 says otherwise; I would ask first.
- **Money:** zero until Phase 7; then the estimates above, each behind a dry-run estimate and your OK.
