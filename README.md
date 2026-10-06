# fedproc-ledger

Which FAR/DFARS clauses actually bind a US federal solicitation, and how (incorporated by reference, full text, selected in a checklist), at which date and alternate, with the page and sentence that prove it.

**Status: Phase 0 (scaffold).** No data has been collected and there are no results yet. This README will state numbers only after they are produced by code in this repo and written to `results/`.

- Plan: [`docs/PLAN.md`](docs/PLAN.md) · execution plan and phase map: [`docs/EXECUTION_PLAN.md`](docs/EXECUTION_PLAN.md) · decisions: [`docs/decisions.md`](docs/decisions.md)
- Rules for contributors and agents: [`CLAUDE.md`](CLAUDE.md)

```bash
uv sync --extra ml --group dev
uv run fl --help
uv run pytest -q
```

Not legal advice and not a compliance determination. Licence: Apache-2.0.
