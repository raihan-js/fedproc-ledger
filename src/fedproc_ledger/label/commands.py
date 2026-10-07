"""`fl label ...`: panel votes over the rules-stage candidates (D-019)."""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import typer

from fedproc_ledger.label import panel as P
from fedproc_ledger.paths import PROCESSED, RESULTS
from fedproc_ledger.rules import sections as S

label_app = typer.Typer(help="Panel labeler: local models vote on each candidate's role (D-019).", no_args_is_help=True)
OUT = PROCESSED / "panel"
CACHE = Path("data/interim/panel_cache.jsonl")


def _text(v: Any) -> str | None:
    """A string, or None for None / NaN / empty (pandas hands back NaN, which is truthy)."""
    return None if v is None or (isinstance(v, float) and v != v) or v == "" else str(v)


def build_items(doc_id: str) -> list[dict[str, Any]]:
    """Candidates of one document with neutral context: surrounding lines and the headings above (no B1 output)."""
    cands = pd.read_parquet(PROCESSED / "rules" / f"{doc_id}.parquet")
    shard = pd.read_parquet(PROCESSED / "pages" / f"{doc_id}.parquet", columns=["page", "text_layout"]).sort_values(
        "page"
    )
    pages = {int(str(r.page)): str(r.text_layout).split("\n") for r in shard.itertuples()}
    heads = [
        (ln.page, ln.line_no, ln.text)
        for ln in S.label_document([(p, "\n".join(ls)) for p, ls in pages.items()])
        if ln.heading
    ]
    items = []
    for c in cands.itertuples():
        if bool(c.from_range):
            continue  # range copies inherit the role of the range's first number
        before = [t for pg, ln, t in heads if (pg, ln) < (int(str(c.page)), int(str(c.line_no)))][-3:]
        lines = pages[int(str(c.page))]
        items.append(
            {
                "id": str(c.cand_id),
                "number": str(c.number),
                "alternate": _text(c.alternate),
                "cited_date": _text(c.cited_date),
                "breadcrumb": [t[:80] for t in before],
                "context": P.context_text(lines, int(str(c.line_no)), str(c.raw)),
                "b1": str(c.role),
            }
        )
    return items


def chat_for(backend: str, base_url: str) -> P.Chat:
    """`local` = an OpenAI-compatible server at base_url; `openai` = the OpenAI API with logging and a spend cap."""
    if backend == "openai":
        from fedproc_ledger.label.openai_chat import make_openai_chat

        return make_openai_chat(P.schema())
    return make_chat(base_url)


def make_chat(base_url: str, timeout: float = 300.0) -> P.Chat:
    client = httpx.Client(base_url=base_url, timeout=timeout)

    def chat(model: str, messages: list[dict[str, str]]) -> str:
        body = {
            "model": model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": 1200,
            "response_format": {"type": "json_schema", "json_schema": {"name": "labels", "schema": P.schema()}},
        }
        for attempt in range(3):
            try:
                r = client.post("/chat/completions", json=body)
                r.raise_for_status()
                return str(r.json()["choices"][0]["message"]["content"])
            except (httpx.HTTPError, KeyError):
                if attempt == 2:
                    raise
        return ""

    return chat


@label_app.command()
def run(
    voter: str = typer.Option(
        ..., help="name:model:variant, for example 9b-A:qwen3.5:9b:A (model may contain a colon)"
    ),
    base_url: str = typer.Option("http://127.0.0.1:11600/v1"),
    backend: str = typer.Option("local", help="local | openai"),
    docs: str = typer.Option("", help="file with one doc_id per line (default: every rules-stage document)"),
    limit: int = typer.Option(0),
    workers: int = typer.Option(4),
) -> None:
    """Run one voter over documents; votes are saved per document and calls are cached (safe to re-run)."""
    name, rest = voter.split(":", 1)
    model, variant = rest.rsplit(":", 1)
    v = P.Voter(name, model, variant)
    ids = (
        [x.strip() for x in Path(docs).read_text().splitlines() if x.strip()]
        if docs
        else sorted(p.stem for p in (PROCESSED / "rules").glob("*.parquet") if not p.stem.startswith("_"))
    )
    if limit:
        ids = ids[:limit]
    (OUT / "votes").mkdir(parents=True, exist_ok=True)
    cache, chat = P.Cache(CACHE), chat_for(backend, base_url)

    def one(doc_id: str) -> tuple[str, int]:
        path = OUT / "votes" / f"{doc_id}.{v.name}.json"
        if path.exists():
            return doc_id, -1
        items = build_items(doc_id)
        got = P.vote(items, v, chat, cache)
        path.write_text(json.dumps(got), encoding="utf-8")
        return doc_id, len(got)

    done = 0
    with ThreadPoolExecutor(workers) as ex:
        for doc_id, n in ex.map(one, ids):
            done += 1
            typer.echo(f"[{done}/{len(ids)}] {doc_id} {'cached' if n < 0 else f'{n} votes'}")


@label_app.command()
def merge(docs: str = typer.Option("", help="file with doc ids (default: documents that have votes)")) -> None:
    """Combine saved votes with B1 into data/processed/panel/<doc>.parquet and write results/panel_stats.json."""
    files = sorted((OUT / "votes").glob("*.json"))
    by_doc: dict[str, dict[str, dict[str, str]]] = {}
    for f in files:
        doc_id, vname = f.stem.rsplit(".", 1)
        by_doc.setdefault(doc_id, {})[vname] = json.loads(f.read_text())
    if docs:
        keep = set(Path(docs).read_text().split())
        by_doc = {d: v for d, v in by_doc.items() if d in keep}
    rows = []
    for doc_id, voters in by_doc.items():
        items = build_items(doc_id)
        for it in items:
            votes = {n: v[it["id"]] for n, v in voters.items() if it["id"] in v}
            votes["b1"] = it["b1"]
            adj = P.adjudicate(votes)
            rows.append(
                {"doc_id": doc_id, "cand_id": it["id"], "number": it["number"], **adj, "votes": json.dumps(votes)}
            )
    df = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT / "panel.parquet", index=False)
    names = sorted({n for v in by_doc.values() for n in v})
    kappas = {}
    vv = [json.loads(x) for x in df["votes"]] if len(df) else []
    for i, a in enumerate(names + ["b1"]):
        for b in (names + ["b1"])[i + 1 :]:
            pairs = [(x[a], x[b]) for x in vv if a in x and b in x]
            kappas[f"{a}~{b}"] = {
                "n": len(pairs),
                "kappa": P.pairwise_kappa([p for p, _ in pairs], [q for _, q in pairs]),
            }
    stats = {
        "documents": len(by_doc),
        "mentions": len(df),
        "tiers": df["tier"].value_counts().to_dict() if len(df) else {},
        "roles": df["role"].value_counts().to_dict() if len(df) else {},
        "kappa": kappas,
    }
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "panel_stats.json").write_text(json.dumps(stats, indent=1, default=float) + "\n", encoding="utf-8")
    typer.echo(json.dumps(stats, indent=1, default=float))


@label_app.command()
def pilot(docs: str = typer.Option("data/interim/pilot_docs.txt")) -> None:
    """Pilot report: B0 and B1 against the panel ledger; panel members against objective checkbox truth (slice A)."""
    from fedproc_ledger.candidates.patterns import extract_clause_numbers
    from fedproc_ledger.label import pilot as PL
    from fedproc_ledger.rules import baseline as B
    from fedproc_ledger.rules.commands import load_registry

    ids = [x for x in Path(docs).read_text().split() if x]
    panel_df = pd.read_parquet(OUT / "panel.parquet")
    registry = load_registry()
    per_doc: dict[str, Any] = {}
    a_pred: dict[str, list[str]] = {}
    a_truth: list[str] = []
    for doc_id in ids:
        rules = pd.read_parquet(PROCESSED / "rules" / f"{doc_id}.parquet")
        alt = dict(zip(rules["cand_id"], rules["alternate"], strict=True))
        mine = panel_df[panel_df["doc_id"] == doc_id]
        gold, uncertain = PL.panel_ledger([{str(k): v for k, v in r.items()} for r in mine.to_dict("records")], alt)
        b1 = {
            (str(r.number), r.alternate or None)
            for r in rules.itertuples()
            if r.role in B.BINDING and not bool(r.from_range)
        }
        excl = {str(r.number) for r in rules.itertuples() if r.role == B.EXCLUDED}
        b1 = {k for k in b1 if k[0] not in excl}
        shard = pd.read_parquet(PROCESSED / "pages" / f"{doc_id}.parquet", columns=["text_plain"])
        plain = "\n".join(str(t) for t in shard["text_plain"])
        b0 = {
            (n, None)
            for n in (
                B.b0_ledger(extract_clause_numbers(plain), registry) if registry else extract_clause_numbers(plain)
            )
        }
        per_doc[doc_id] = {"gold": gold, "uncertain": uncertain, "systems": {"B0": b0, "B1": b1}}
        pages = pd.read_parquet(PROCESSED / "pages" / f"{doc_id}.parquet", columns=["page", "text_layout"])
        items_at = PL.checklist_item_keys(
            [(int(str(r.page)), str(r.text_layout)) for r in pages.sort_values("page").itertuples()]
        )
        first = rules.sort_values("char_start").groupby(["page", "line_no"])["cand_id"].first()
        firsts = set(first.astype(str))
        votes = {str(r.cand_id): json.loads(str(r.votes)) for r in mine.itertuples()}
        for r in rules.itertuples():
            truth = PL.slice_a_truth(
                str(r.box_marker) if r.box_marker else None,
                (int(str(r.page)), int(str(r.line_no))) in items_at and str(r.cand_id) in firsts,
            )
            if truth and str(r.cand_id) in votes:
                a_truth.append(truth)
                for name, role in votes[str(r.cand_id)].items():
                    a_pred.setdefault(name, []).append(role)
    scores = PL.score_systems(per_doc)
    a_scores = {n: PL.role_agreement(p, a_truth) for n, p in a_pred.items() if len(p) == len(a_truth)}
    stats = json.loads((RESULTS / "panel_stats.json").read_text()) if (RESULTS / "panel_stats.json").exists() else {}
    report = {
        "documents": len(ids),
        "panel": stats,
        "ledger_vs_panel": scores,
        "slice_a": {"n": len(a_truth), "per_voter": a_scores},
        "decision": PL.decide(scores["B0"]["precision"], scores["B1"]["f"]),
        "note": "References are panel-adjudicated, not human gold (D-019); slice A is objective but B1 reads the same glyphs.",
    }
    (RESULTS / "pilot.json").write_text(PL.dumps(report) + "\n", encoding="utf-8")
    typer.echo(PL.dumps({k: report[k] for k in ("ledger_vs_panel", "slice_a", "decision")}))


def slice_a_ids(doc_id: str) -> dict[str, str]:
    """Candidate id -> objective truth (SELECTED / NOT_SELECTED) for checklist item lines of one document: glyph boxes
    (⟦X⟧ / ⟦ ⟧) and typed forms ("__ (43)", "X (44)", "[ ]", "[X]"), decided on the first candidate of the line."""
    from fedproc_ledger.label import pilot as PL

    rules = pd.read_parquet(PROCESSED / "rules" / f"{doc_id}.parquet")
    pg = pd.read_parquet(PROCESSED / "pages" / f"{doc_id}.parquet", columns=["page", "text_layout"]).sort_values("page")
    keys = PL.checklist_item_keys([(int(str(r.page)), str(r.text_layout)) for r in pg.itertuples()])
    first = set(rules.sort_values("char_start").groupby(["page", "line_no"])["cand_id"].first().astype(str))
    out = {}
    for r in rules.itertuples():
        if str(r.cand_id) not in first or bool(r.from_range):
            continue
        on_item = (int(str(r.page)), int(str(r.line_no))) in keys
        truth = PL.slice_a_truth(str(r.box_marker) if r.box_marker else None, on_item)
        if truth is None:
            line = str(r.line_text)
            pos = line.find(str(r.raw))
            if 0 <= pos <= 40:  # the number sits right after the "__ (43)" / "X (44)" prefix
                truth = PL.typed_item_state(line)
        if truth:
            out[str(r.cand_id)] = truth
    return out


_PARA_A_START = re.compile(
    r"^\s*\(a\)\s+The Contractor shall comply with the following (?:Federal Acquisition Regulation|FAR)", re.I
)
_PARA_A_END = re.compile(r"^\s*\(b\)\s+\S")
_PARA_A_ITEM = re.compile(r"^\s*\(\d{1,2}\)\s*(?:FAR\s+)?\d")


def para_a_ids(doc_id: str) -> set[str]:
    """Candidate ids that sit in the unconditional paragraph (a) of FAR 52.212-5: numbered items "(1) 52.203-19, ..." with no
    checkbox. Amendment A2 (docs/preregistration_round2.md) reads them as binding wherever 52.212-5 is incorporated or included.
    The span runs from "(a) The Contractor shall comply with the following FAR clauses" to the next "(b)" line (at most 150 lines)."""
    rules = pd.read_parquet(PROCESSED / "rules" / f"{doc_id}.parquet")
    pg = pd.read_parquet(PROCESSED / "pages" / f"{doc_id}.parquet", columns=["page", "text_layout"]).sort_values("page")
    span: set[tuple[int, int]] = set()
    active, used = False, 0
    for r in pg.itertuples():
        for i, ln in enumerate(str(r.text_layout).split("\n")):
            if not active and _PARA_A_START.match(ln):
                active, used = True, 0
            elif active:
                used += 1
                if _PARA_A_END.match(ln) or used > 150:
                    active = False
                elif _PARA_A_ITEM.match(ln) and "\u27e6" not in ln:
                    span.add((int(str(r.page)), i))
    out = set()
    for c in rules.itertuples():
        if bool(c.from_range):
            continue
        if (int(str(c.page)), int(str(c.line_no))) in span and str(c.line_text).find(str(c.raw)) <= 16:
            out.add(str(c.cand_id))
    return out


_PARENT = re.compile(r"^\s*(?P<m>_*X+_*|\[X\]|\u27e6X\u27e7|_{2,}|\[\s*\]|\u27e6 \u27e7)\s*\(\d{1,3}\)\s*$")
_CHILD = re.compile(r"^\s*\u27e6\?\u27e7\s*\((?:i|ii|iii|iv|v|vi)\)")
_BLOCK27 = re.compile(r"^\s*\u27e6(?P<m>X| )\u27e7\s*27[ab]\.")


def inherited_ids(doc_id: str) -> dict[str, str]:
    """Candidate id -> SELECTED / NOT_SELECTED for two layouts the plain box rule cannot read: (1) a sub-item "⟦?⟧ (i) 52.x"
    whose marker was lost takes the state of its parent line "__ (35)" / "X (36)" within the previous three lines; (2) SF 1449
    blocks 27a and 27b: the glyph at the start of the block decides every candidate up to the next glyph line."""
    rules = pd.read_parquet(PROCESSED / "rules" / f"{doc_id}.parquet")
    pg = pd.read_parquet(PROCESSED / "pages" / f"{doc_id}.parquet", columns=["page", "text_layout"]).sort_values("page")
    state: dict[tuple[int, int], str] = {}
    for r in pg.itertuples():
        lines = str(r.text_layout).split("\n")
        block: str | None = None
        for i, ln in enumerate(lines):
            m27 = _BLOCK27.match(ln)
            if m27:
                block = "CHECKLIST_SELECTED" if m27.group("m") == "X" else "CHECKLIST_NOT_SELECTED"
                state[(int(str(r.page)), i)] = block
                continue
            if block and ln.lstrip().startswith("\u27e6"):
                block = None
            elif block:
                state[(int(str(r.page)), i)] = block
            if _CHILD.match(ln):
                for back in range(1, 4):
                    pm = _PARENT.match(lines[i - back]) if i - back >= 0 else None
                    if pm:
                        sel = "X" in pm.group("m")
                        state[(int(str(r.page)), i)] = "CHECKLIST_SELECTED" if sel else "CHECKLIST_NOT_SELECTED"
                        break
    out = {}
    first = set(rules.sort_values("char_start").groupby(["page", "line_no"])["cand_id"].first().astype(str))
    for c in rules.itertuples():
        key = (int(str(c.page)), int(str(c.line_no)))
        if not bool(c.from_range) and key in state and (str(c.cand_id) in first or state[key]):
            out[str(c.cand_id)] = state[key]
    return out


@label_app.command()
def lab(
    voter: str = typer.Option(..., help="name:model:variant"),
    base_url: str = typer.Option("http://127.0.0.1:11600/v1"),
    backend: str = typer.Option("local", help="local | openai"),
    docs: str = typer.Option("data/interim/pilot_docs.txt"),
) -> None:
    """Score one voter configuration on slice A only (objective checklist boxes) and log it to the leaderboard."""
    from fedproc_ledger.eval.leaderboard import log_run
    from fedproc_ledger.label import pilot as PL

    name, rest = voter.split(":", 1)
    model, variant = rest.rsplit(":", 1)
    v = P.Voter(name, model, variant)
    cache, chat = P.Cache(CACHE), chat_for(backend, base_url)
    pred: list[str] = []
    truth: list[str] = []
    for doc_id in [x for x in Path(docs).read_text().split() if x]:
        a = slice_a_ids(doc_id)
        if not a:
            continue
        items = [i for i in build_items(doc_id) if i["id"] in a]
        got = P.vote(items, v, chat, cache)
        for i in items:
            pred.append(got.get(i["id"], "UNCLEAR"))
            truth.append(a[i["id"]])
    res = PL.role_agreement(pred, truth)
    log_run(
        RESULTS / "leaderboard.jsonl",
        f"slice-A {v.name}",
        {"model": model, "variant": variant},
        res,
        split="pilot-slice-a",
    )
    typer.echo(json.dumps(res))


@label_app.command()
def audit(
    voter: str = typer.Option("", help="name:model:variant (empty = score B1 only)"),
    base_url: str = typer.Option("http://127.0.0.1:11600/v1"),
    backend: str = typer.Option("local", help="local | openai"),
    labels: str = typer.Option("results/audit_claude_pilot.json"),
) -> None:
    """Score one voter (and B1) against the agent-labelled audit set; UNCLEAR audit labels are excluded."""
    from fedproc_ledger.eval.leaderboard import log_run
    from fedproc_ledger.label import pilot as PL

    ref = json.loads(Path(labels).read_text())["labels"]
    ref = {k: v for k, v in ref.items() if v != "UNCLEAR"}
    docs = sorted({k.rsplit("-p", 1)[0] for k in ref})
    items = [i for d in docs for i in build_items(d) if i["id"] in ref]
    truth = [ref[i["id"]] for i in items]
    out: dict[str, Any] = {"n": len(items), "b1": PL.role_agreement([i["b1"] for i in items], truth)}
    if voter:
        name, rest = voter.split(":", 1)
        model, variant = rest.rsplit(":", 1)
        v = P.Voter(name, model, variant)
        got = P.vote(items, v, chat_for(backend, base_url), P.Cache(CACHE))
        out[name] = PL.role_agreement([got.get(i["id"], "UNCLEAR") for i in items], truth)
        log_run(
            RESULTS / "leaderboard.jsonl",
            f"audit {name}",
            {"model": model, "variant": variant},
            out[name],
            split="pilot-audit",
        )
    typer.echo(json.dumps(out))
