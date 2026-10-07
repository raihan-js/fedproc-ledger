# FedProc-Ledger integration — agent instruction file (VETR Framework)

> **For:** an AI coding agent working inside the VETR-Framework repository (Laravel/PHP), with the CTO in the loop.
> **Goal:** connect the public FedProc-Ledger clause-ledger model to the VETR application behind a feature flag, shadow it, and only then let it influence customer-visible output.
> **Read first:** the research contract `https://github.com/raihan-js/fedproc-ledger/blob/main/docs/INTEGRATION_CONTRACT.md` (v0.3). Everything numbered below (scores, thresholds, acceptance gates) comes from that repo's `results/*.json`.
> **Rules for this integration:** never edit the research repository from here; never send customer documents outside the VPC; the ledger sidecar is deterministic CPU code, not an LLM call — do not route it through any AI provider. Ask the CTO before enabling the flag for any customer.

## 0. What you are integrating

FedProc-Ledger answers one question about a solicitation document: **which FAR/DFARS clause numbers bind the contract** (incorporated by reference, full text included, or a selected checklist item), each with a probability `q`, a tier, and evidence lines. Measured value over the status-quo regexes (four consecutive pre-registered rounds on fresh documents, majority gold of one agent + two judges): binding-set F1 +0.08 to +0.14 with intervals above zero, specificity 70–79% vs 8–19% at equal recall. Annotator-free audit: ~13.8% of regex ledger entries are clauses whose own checklist box is empty. Limits that constrain this plan: no human-expert labels yet (a 200-document reviewer gold is being labelled), numbers only (no alternates/dates), scanned PDFs return no ledger.

Public artefacts: model `https://huggingface.co/raihan-js/fedproc-ledger-v1` (0.46 MB numpy weights, Apache-2.0), data `https://huggingface.co/datasets/raihan-js/fedproc-ledger-bench`, paper draft in the research repo (`release/paper/main.pdf`, submitted to arXiv).

## 1. Architecture (do not change this shape)

```
VETR worker ── stores RFP bytes (unchanged)
    │ ParseRfpDocument succeeds (unchanged)
    ▼
NEW BuildClauseLedger job ──POST file bytes──▶ ledger sidecar (FastAPI, CPU-only, in-VPC ECS service)
    │                                          returns contract_version "0.3" JSON (§3)
    ▼
NEW tables rfp_clause_ledgers / rfp_clause_entries (feature-flagged reads)
    │
    ├── FarClauseDetectionService: ledger entries feed `matched`; regex stays as fallback
    └── FarClauseController::solicitationContext: is_commercial from derived facts (else null, as today)
```

Why a sidecar and not PHP code: the ledger needs its own PDF/DOCX extraction (VETR's Smalot-based text loses checkbox state — measured), the eCFR registry, and the numpy scorer. PHP cannot run that stack. The sidecar makes **no outbound calls**, stores nothing, logs no document text — so the Bedrock-only boundary (`AiProviderFactory::bedrockOnly()`, `config/ai.php:bedrock_only`, on by default in production) does not apply to it. Note that explicitly in the deployment review.

## 2. The sidecar API (frozen as contract 0.3 — code against these fields, not the research repo)

- `GET /healthz` → `{"status": "ok"}`. Bake the model + registry into the image; no downloads at boot; no outbound network.
- `POST /v1/ledger` — multipart `file` (.pdf/.docx/.doc/.txt, else 415) + optional form `posted_date: YYYY-MM-DD` (enables version-currency; RFO-era postings ≥ 2025-10-28 are reported, not judged).
- Response: `contract_version` (`"0.3"` — reject anything else), `model: {name, sha256, rules_version ("1.4"), aggregation}`, `document: {pages, scanned, extraction_warnings, candidates}`, `entries[]: {number, alternate, tier (BINDING if q≥0.7, NOT_BINDING if q≤0.3, else UNDETERMINED), q, decided_by (model | box_rule | para_a_rule | text_rule | list_rule | excluded_rule), registry: {status, cited_date, version_in_force, currency}, evidence[]: {page, line, role, p, source, text} (≤5)}`, `summary: {binding, not_binding, undetermined, rule_decided_share}`.
- `scanned: true` means no text layer: store the flag, produce no entries, never treat as "no clauses".

## 3. Work phases (in order; each ends with its checks green before the next starts)

### Phase 1 — sidecar image + staging deploy
1. Dockerfile: python 3.11 slim, install the research repo (`pip install -e .` needs `serve` deps: fastapi, uvicorn, python-multipart — see its `pyproject.toml`), run `uvicorn fedproc_ledger.serve.app:app` on the container port.
2. Smoke test (no customer data): POST a public SAM.gov solicitation PDF, assert `contract_version == "0.3"`, `entries` non-empty, every entry has `evidence[]`.
3. Deploy as a **new ECS service in the existing VPC** (`infrastructure/aws/cloudformation.yml`, GovCloud us-gov-west-1). Start at 1 vCPU / 2 GB (the current 0.25 vCPU worker task is too small for extraction + inference); keep it in private subnets, security group accepts only the worker tasks. Record p50/p95 latency over 50 public documents.

### Phase 2 — storage + job (flagged off)
1. Migration: `rfp_clause_ledgers` (id, rfp_id, document_id, model_sha256, rules_version, posted_date, summary JSON, error nullable, timestamps) and `rfp_clause_entries` (ledger_id, number, alternate nullable, tier, q, decided_by, registry JSON, evidence JSON). Index `(rfp_id)`.
2. `app/Jobs/BuildClauseLedger.php`: takes the stored document bytes (same bytes `ParseRfpDocument` received — do not re-extract in PHP), POSTs to the sidecar with a 120 s timeout, writes the ledger, records sidecar errors on the ledger row (never throws into the parse pipeline).
3. Dispatch it where `ImportRfpFromUrl` dispatches `ParseRfpDocument` (that file, ~line 178: `ParseRfpDocument::dispatch($this->rfp->fresh(), $document)`), chained to run **after** a successful parse, gated on a plan feature flag (`PlanLimitService::hasFeature($org, 'clause_ledger')` — the repo's convention, cf. `AgentRunner`), default off.
4. PHP tests: job stores entries for a canned sidecar response (use a recorded fixture, never a live call); sidecar-down writes `error` and leaves regex behavior untouched; scanned flag produces no entries.

### Phase 3 — detection service (fallback preserved)
1. In `FarClauseDetectionService` (the `detectFromText` / `detectForProposal` path): when a ledger exists for the RFP **and** the flag is on, build `matched` from ledger BINDING entries, expose the rest as `not_binding`, keep `unmatched`/`required` semantics. When no ledger exists, the flag is off, or the sidecar errored: byte-identical behavior to today (prove with the existing tests plus a ledger-present/ledger-absent pair).
2. Never silently drop a clause the regex found: any regex number missing from the ledger appears in the response with its tier (usually UNDETERMINED) so the UI can show "needs review" instead of hiding it.

### Phase 4 — controller context + UI
1. `FarClauseController::solicitationContext()`: set `is_commercial` from the ledger's derived facts **only when present with evidence**; otherwise keep `null` (today's behavior — the comment there explains why defaulting is wrong).
2. Far-compliance page: per clause show status, cited date + date status, and the evidence snippet; separate "Provisions (answer in your offer)" from "Clauses (comply after award)"; surface UNDETERMINED and low-margin entries for human review, never auto-resolve them.

### Phase 5 — shadow mode, then the acceptance gate
1. Four weeks minimum with the flag on for internal/test orgs only: log every difference (entries only the model includes or excludes), review a weekly sample, watch drift monitors (share of box-rule decisions, mean `q`, UNDETERMINED share, scanned share; alert past 10 points).
2. Score the frozen model against the 200-document VETR reviewer gold (being labelled; criteria pre-registered in the research repo): **A1** non-inferior F1 (margin −0.03), **A2** recall within 3 points of the regexes, **A3** specificity ≥ 0.50. Customer-visible use only if all three hold. If any fails, the errors go back as the v1.5 development set — do not tune thresholds on this gold.

## 4. Rollback (per phase)

- Phase 1/2: stop dispatching the job; nothing customer-visible changes (reads are flag-gated).
- Phase 3/4: flag off restores byte-identical regex behavior (covered by the Phase-3 pair tests).
- Data: ledger tables are additive; dropping them never affects existing columns.

## 5. Glossary (terms the VETR code will store)

- **Binding set**: numbers with tier BINDING. **q**: max over the number's mention probabilities. **decided_by**: which rule or the model set the mention; `box_rule`/`para_a_rule`/`list_rule`/`text_rule`/`excluded_rule` are deterministic, `model` is the classifier. **currency**: cited clause date vs the eCFR version in force on the posting day (CURRENT / SUPERSEDED / NEWER_THAN_ECFR / UNKNOWN_DATE / DEVIATION_MARKED). **UNDETERMINED**: q between 0.3 and 0.7 — route to a person, never to a verdict.
