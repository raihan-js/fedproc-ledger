"""`fl rules ...`: candidates, section labels and the B1 / B0 baselines over the extracted documents (Phase 4)."""

from __future__ import annotations

import html
import json
from typing import Any

import pandas as pd
import typer

from fedproc_ledger.candidates.generate import generate_page_candidates
from fedproc_ledger.candidates.patterns import extract_clause_numbers
from fedproc_ledger.paths import DATA, PROCESSED, RESULTS
from fedproc_ledger.rules import baseline as B
from fedproc_ledger.rules import sections as S

rules_app = typer.Typer(
    help="Phase 4: candidates, section labels, rules baseline B1 and status-quo B0.", no_args_is_help=True
)
OUT = PROCESSED / "rules"
PAGES = PROCESSED / "pages"


def load_registry() -> dict[str, str] | None:
    path = PROCESSED / "registry.parquet"
    if not path.exists():
        return None
    df = pd.read_parquet(path, columns=["number", "status"])
    return dict(zip(df["number"], df["status"], strict=True))


def run_document(doc_id: str, registry: dict[str, str] | None) -> dict[str, Any]:
    shard = pd.read_parquet(PAGES / f"{doc_id}.parquet", columns=["page", "text_layout", "text_plain"]).sort_values(
        "page"
    )
    pages = [(int(str(r.page)), str(r.text_layout)) for r in shard.itertuples()]
    cands = [c for p, t in pages for c in generate_page_candidates(doc_id, p, t, registry)]
    labelled = S.label_document(pages)
    preds = B.classify_document(cands, labelled)
    rows = []
    for p in preds:
        c = p.cand
        rows.append(
            {**c.as_row(), "role": p.role, "confidence": p.confidence, "reason": p.reason, "section": p.section}
        )
    led = B.ledger(preds)
    plain = "\n".join(str(t) for t in shard["text_plain"])
    b0 = B.b0_ledger(extract_clause_numbers(plain), registry) if registry else set(extract_clause_numbers(plain))
    mention_numbers = {c.number for c in cands if not c.from_range}
    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(OUT / f"{doc_id}.parquet", index=False)
    return {
        "doc_id": doc_id,
        "pages": len(pages),
        "candidates": len(cands),
        "distinct_numbers": len(mention_numbers),
        "roles": dict(pd.Series([r["role"] for r in rows]).value_counts()) if rows else {},
        "b1_ledger": len(led),
        "b0_ledger": len(b0),
        "b1_ledger_numbers": sorted({k[0] for k in led}),
    }


@rules_app.command()
def run(limit: int = typer.Option(0, help="At most this many documents (0 = all extracted)")) -> None:
    """Candidates + sections + B1 + B0 for each extracted document (re-runs everything: rules change often)."""
    registry = load_registry()
    typer.echo("registry: " + ("loaded" if registry else "NOT available (candidates are not checked against eCFR)"))
    ids = sorted(p.stem for p in PAGES.glob("*.parquet"))
    if limit:
        ids = ids[:limit]
    summaries = [run_document(i, registry) for i in ids]
    RESULTS.mkdir(exist_ok=True)
    tot_roles: dict[str, int] = {}
    for s in summaries:
        for k, v in s["roles"].items():
            tot_roles[k] = tot_roles.get(k, 0) + int(v)
    agg = {
        "documents": len(summaries),
        "registry_used": registry is not None,
        "candidates": sum(s["candidates"] for s in summaries),
        "b1_roles": dict(sorted(tot_roles.items())),
        "documents_with_candidates": sum(1 for s in summaries if s["candidates"]),
        "b0_ledger_total": sum(s["b0_ledger"] for s in summaries),
        "b1_ledger_total": sum(s["b1_ledger"] for s in summaries),
    }
    (RESULTS / "rules_stats.json").write_text(json.dumps(agg, indent=1) + "\n", encoding="utf-8")
    pd.DataFrame(summaries).drop(columns=["b1_ledger_numbers"]).to_parquet(OUT / "_summary.parquet", index=False)
    typer.echo(json.dumps(agg, indent=1))


_ROLE_CLASS = {
    B.SELECTED: "ok",
    B.IBR: "ok",
    B.FULL: "ok",
    B.NOT_SELECTED: "no",
    B.NARRATIVE: "no",
    B.INTERNAL: "no",
    B.INDEX: "no",
    B.NOT_CLAUSE: "no",
    B.EXCLUDED: "no",
}


@rules_app.command()
def report(docs: int = typer.Option(5, help="Number of documents to show")) -> None:
    """HTML table (data/reports/rules_report.html): candidate, line, section and predicted role for a few documents."""
    docinfo = pd.read_parquet(DATA / "interim" / "documents.parquet").drop_duplicates("doc_id").set_index("doc_id")
    summary = pd.read_parquet(OUT / "_summary.parquet")
    # a spread: documents with the most candidates, a checklist-heavy one, and a middle one
    big = summary.sort_values("candidates", ascending=False)
    pick = list(
        dict.fromkeys(list(big.head(2)["doc_id"]) + list(big.iloc[len(big) // 2 : len(big) // 2 + 3]["doc_id"]))
    )[:docs]
    parts = [
        "<!doctype html><meta charset='utf-8'><style>body{font:13px system-ui;margin:20px}table{border-collapse:collapse;margin:8px 0 28px}td,th{border:1px solid #ddd;padding:3px 7px;vertical-align:top}"
        ".ok{background:#e4f6e8}.no{background:#f3f3f3}.low{color:#b45f00}code{font-size:12px}</style><h1>Rules baseline B1 on real documents</h1>"
    ]
    for doc_id in pick:
        df = pd.read_parquet(OUT / f"{doc_id}.parquet")
        name = docinfo.loc[doc_id, "filename"] if doc_id in docinfo.index else doc_id
        s = summary[summary["doc_id"] == doc_id].iloc[0]
        parts.append(
            f"<h2>{html.escape(str(name))}</h2><p>{int(s['candidates'])} candidates, {int(s['distinct_numbers'])} distinct numbers; B0 (status quo) binds {int(s['b0_ledger'])}, B1 binds {int(s['b1_ledger'])}.</p>"
        )
        parts.append(
            "<table><tr><th>page</th><th>number</th><th>role</th><th>conf</th><th>section</th><th>why</th><th>line</th></tr>"
        )
        for r in df.sort_values(["page", "char_start"]).head(70).itertuples():
            cls = _ROLE_CLASS.get(str(r.role), "")
            conf = float(str(r.confidence))
            low = " low" if conf < 0.7 else ""
            parts.append(
                f"<tr class='{cls}'><td>{r.page}</td><td><code>{html.escape(str(r.number))}</code></td><td>{r.role}</td><td class='{low.strip()}'>{conf:.2f}</td><td>{r.section}</td><td>{html.escape(str(r.reason))}</td><td>{html.escape(str(r.line_text)[:140])}</td></tr>"
            )
        parts.append("</table>")
    out = DATA / "reports" / "rules_report.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(parts), encoding="utf-8")
    typer.echo(f"wrote {out} ({len(pick)} documents)")
