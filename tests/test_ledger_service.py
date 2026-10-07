"""End-to-end smoke test of the single-document ledger (skipped when the trained model file is not present)."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fedproc_ledger.model.commands import MODEL

pytestmark = pytest.mark.skipif(not Path(MODEL).exists(), reason="data/models/role_model.pkl not built")

TEXT = """CLAUSES INCORPORATED BY REFERENCE
52.204-21
Basic Safeguarding of Covered Contractor Information Systems (NOV 2021)
52.212-4
Contract Terms and Conditions - Commercial Products and Commercial Services (NOV 2023)
__ (35) 52.222-35, Equal Opportunity for Veterans (JUN 2020) (38 U.S.C. 4212).
X (36) 52.222-36, Equal Opportunity for Workers with Disabilities (JUN 2020) (29 U.S.C. 793).
"""


def test_ledger_for_text_file(tmp_path):
    from fedproc_ledger.serve.ledger import ledger_for_file

    p = tmp_path / "sol.txt"
    p.write_text(TEXT)
    out = ledger_for_file(p)
    by = {e["number"]: e for e in out["entries"]}
    assert out["contract_version"] == "0.2" and out["document"]["scanned"] is False
    assert by["52.222-35"]["tier"] == "NOT_BINDING" and by["52.222-35"]["decided_by"] == "box_rule"
    assert by["52.222-36"]["tier"] == "BINDING" and by["52.222-36"]["decided_by"] == "box_rule"
    assert by["52.204-21"]["tier"] == "BINDING"
    assert json.dumps(out)  # serialisable


def test_http_endpoint_rejects_unknown_type_and_serves_txt():
    from fedproc_ledger.serve.app import app

    c = TestClient(app)
    assert c.get("/healthz").json() == {"status": "ok"}
    assert c.post("/v1/ledger", files={"file": ("x.exe", b"abc")}).status_code == 415
    r = c.post("/v1/ledger", files={"file": ("sol.txt", TEXT.encode())})
    assert r.status_code == 200 and r.json()["summary"]["binding"] >= 2
