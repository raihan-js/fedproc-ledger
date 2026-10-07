"""`fl serve`: POST /v1/ledger with an uploaded file returns the clause ledger (docs/INTEGRATION_CONTRACT.md)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from fedproc_ledger.serve.ledger import ledger_for_file

app = FastAPI(title="fedproc-ledger", version="0.2")
_ALLOWED = {".pdf", ".docx", ".doc", ".txt"}


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/ledger")
def ledger(file: UploadFile = File(...), posted_date: str | None = Form(None)) -> dict:  # noqa: B008
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ALLOWED:
        raise HTTPException(415, f"unsupported type {suffix or '(none)'}; use one of {sorted(_ALLOWED)}")
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / f"upload{suffix}"
        p.write_bytes(file.file.read())
        return ledger_for_file(p, posted_date=posted_date)
