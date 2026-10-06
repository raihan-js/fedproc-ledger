"""Panel labeler (D-019): local models vote on the role of every clause-number candidate; B1 is one more voter.

A model never writes a clause number: it receives candidate ids with context and returns one role per id, as JSON
constrained by a schema. Calls are cached by content hash so a re-run costs nothing.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fedproc_ledger.rules.baseline import BINDING, ROLES

LLM_ROLES = [r for r in ROLES if r != "UNCLEAR"] + ["UNCLEAR"]
CHUNK = 10
MAX_CHARS = (
    9000  # per call (about 3k tokens): a slot holds 8k tokens with the server settings in scripts/llama_server.sh
)


def chunks(items: Sequence[Mapping[str, Any]]) -> list[list[Mapping[str, Any]]]:
    """At most CHUNK items per call and at most MAX_CHARS of context."""
    out: list[list[Mapping[str, Any]]] = []
    cur: list[Mapping[str, Any]] = []
    size = 0
    for it in items:
        n = len(str(it["context"])) + 150
        if cur and (len(cur) >= CHUNK or size + n > MAX_CHARS):
            out.append(cur)
            cur, size = [], 0
        cur.append(it)
        size += n
    return out + [cur] if cur else out


GUIDE = """You label how a clause-number reference is used inside a US federal solicitation (FAR/DFARS).
For each candidate (marked in its context line by >>> <<<) choose exactly one role:
INCORPORATED_BY_REFERENCE: listed as incorporated by reference (a list of clauses/provisions "incorporated by reference", e.g. under 52.252-2 or a Section I/K list).
FULL_TEXT: the heading of a clause/provision whose full text is included in the document.
CHECKLIST_SELECTED: an item of a checklist clause (52.212-5, 52.213-4, 252.212-7001, 52.244-6, agency checklists) that is selected: a marked box [X] / ⟦X⟧ or a list that says these clauses apply.
CHECKLIST_NOT_SELECTED: an item of such a checklist whose box is empty ⟦ ⟧ or marked not applicable.
EXPLICITLY_EXCLUDED: the text says the clause is deleted, reserved, does not apply, or is replaced.
INTERNAL_REFERENCE: cited inside the text of another clause or a prescription ("as defined in 52.204-7", "in accordance with 52.215-1(f)").
NARRATIVE_MENTION: cited in instructions to offerors, evaluation factors, the statement of work or other narrative.
INDEX_ENTRY: table of contents, index, running header or footer.
NOT_A_CLAUSE: the text is not a clause reference (an amount, a version number, a part of a longer number).
UNCLEAR: you cannot decide from the context.
A box ⟦X⟧ is checked, ⟦ ⟧ is empty, ⟦?⟧ is unknown (use UNCLEAR if the role depends on it). Answer with JSON only."""

VARIANT_B_INTRO = (
    "Task: classify each marked clause reference by its role in the solicitation. Think about where in the document the line sits "
    "(headings are given) and whether the contract binds the offeror to that clause. "
)


FEWSHOT = """Examples (context -> role):
headings: 52.212-5 Contract Terms and Conditions Required to Implement Statutes
⟦X⟧ (1) >>>52.219-8<<< Utilization of Small Business Concerns -> CHECKLIST_SELECTED
headings: 52.212-5 Contract Terms and Conditions Required to Implement Statutes
⟦ ⟧ (4) >>>52.222-26<<< Equal Opportunity -> CHECKLIST_NOT_SELECTED
headings: SECTION I - CONTRACT CLAUSES > CLAUSES INCORPORATED BY REFERENCE
>>>52.204-21<<< Basic Safeguarding of Covered Contractor Information Systems (NOV 2021) -> INCORPORATED_BY_REFERENCE
headings: CLAUSES IN FULL TEXT
>>>52.204-21<<< Basic Safeguarding of Covered Contractor Information Systems (NOV 2021)
(a) Definitions. As used in this clause... -> FULL_TEXT
headings: 52.204-13 System for Award Management Maintenance
(b) "Registered in SAM" has the meaning given in >>>52.204-7<<<. -> INTERNAL_REFERENCE
headings: SECTION L - INSTRUCTIONS TO OFFERORS
Offerors shall submit representations in accordance with >>>52.212-1<<<. -> NARRATIVE_MENTION
headings: TABLE OF CONTENTS
>>>52.204-21<<< Basic Safeguarding .............. 45 -> INDEX_ENTRY"""

RULES = """Rules: a line that starts with a box followed (possibly after "(1)") by a clause number is an item of a checklist: ⟦X⟧ -> CHECKLIST_SELECTED, ⟦ ⟧ -> CHECKLIST_NOT_SELECTED, whatever words surround it. The role depends on the line and its headings, not on how common the clause is. Use headings: under "incorporated by reference" lists the role is INCORPORATED_BY_REFERENCE; under "in full text" the clause heading line is FULL_TEXT."""


def schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "labels": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"id": {"type": "string"}, "role": {"type": "string", "enum": LLM_ROLES}},
                    "required": ["id", "role"],
                },
            }
        },
        "required": ["labels"],
    }


@dataclass(frozen=True)
class Voter:
    name: str
    model: str
    variant: str = "A"  # prompt wording; "B" lists the roles in another order and adds an intro


def context_text(lines: Sequence[str], line_no: int, number_raw: str, before: int = 5, after: int = 2) -> str:
    lo, hi = max(0, line_no - before), min(len(lines), line_no + after + 1)
    out = []
    for i in range(lo, hi):
        t = lines[i].strip()
        if i == line_no:
            t = t.replace(number_raw, f">>>{number_raw}<<<", 1) if number_raw in t else f">>> {t} <<<"
        if t:
            out.append(t[:240])
    return "\n".join(out)


def build_prompt(items: Sequence[Mapping[str, Any]], voter: Voter) -> list[dict[str, str]]:
    guide = GUIDE
    if voter.variant in ("B", "C", "D"):
        head, *roles = guide.split("\n")
        body = [r for r in roles if r.split(":")[0] in LLM_ROLES]
        rest = [r for r in roles if r.split(":")[0] not in LLM_ROLES]
        guide = "\n".join([VARIANT_B_INTRO + head, *reversed(body), *rest])
    if voter.variant in ("C", "D"):
        guide = guide + "\n\n" + FEWSHOT + ("\n\n" + RULES if voter.variant == "D" else "")
    blocks = []
    for it in items:
        crumbs = " > ".join(it["breadcrumb"]) or "(no heading seen)"
        extra = "".join(f" [{k}: {it[k]}]" for k in ("alternate", "cited_date") if it.get(k))
        blocks.append(f"id={it['id']} number={it['number']}{extra}\nheadings: {crumbs}\n{it['context']}")
    user = (
        "Candidates:\n\n" + "\n\n".join(blocks) + '\n\nReturn {"labels":[{"id":...,"role":...}]} with one entry per id.'
    )
    return [{"role": "system", "content": guide}, {"role": "user", "content": user}]


def parse_labels(text: str, ids: Sequence[str]) -> dict[str, str]:
    """Role per id; ids the model skipped or invented are dropped (the caller treats a missing id as no vote)."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    got = {}
    for e in data.get("labels", []) if isinstance(data, dict) else []:
        if isinstance(e, dict) and e.get("id") in ids and e.get("role") in LLM_ROLES:
            got[e["id"]] = e["role"]
    return got


class Cache:
    """Append-only JSONL keyed by a hash of (model, messages); thread-safe."""

    def __init__(self, path: Path) -> None:
        self.path, self.lock, self.data = path, threading.Lock(), {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    r = json.loads(line)
                    self.data[r["key"]] = r["text"]

    @staticmethod
    def key(model: str, messages: list[dict[str, str]]) -> str:
        return hashlib.sha256(json.dumps([model, messages], sort_keys=True).encode()).hexdigest()

    def get(self, k: str) -> str | None:
        return self.data.get(k)

    def put(self, k: str, text: str) -> None:
        with self.lock:
            self.data[k] = text
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"key": k, "text": text}, ensure_ascii=False) + "\n")


Chat = Callable[[str, list[dict[str, str]]], str]


def vote(items: Sequence[Mapping[str, Any]], voter: Voter, chat: Chat, cache: Cache | None = None) -> dict[str, str]:
    """One voter's roles for a list of items (chunks of CHUNK per call; a failed parse is retried once per id)."""
    out: dict[str, str] = {}
    for chunk in chunks(items):
        ids = [str(c["id"]) for c in chunk]
        msgs = build_prompt(chunk, voter)
        k = Cache.key(voter.model, msgs)
        text = cache.get(k) if cache else None
        if text is None:
            text = chat(voter.model, msgs)
            if cache:
                cache.put(k, text)
        got = parse_labels(text, ids)
        for missing in [x for x in ids if x not in got]:  # one retry, one id at a time
            one = [c for c in chunk if str(c["id"]) == missing]
            m1 = build_prompt(one, voter)
            k1 = Cache.key(voter.model, m1)
            t1 = cache.get(k1) if cache else None
            if t1 is None:
                t1 = chat(voter.model, m1)
                if cache:
                    cache.put(k1, t1)
            got.update(parse_labels(t1, [missing]))
        out.update(got)
    return out


def adjudicate(votes: Mapping[str, str]) -> dict[str, Any]:
    """votes: voter name -> role (voters that gave none are absent). Tier: unanimous, majority (> half agree), split."""
    if not votes:
        return {"role": "UNCLEAR", "tier": "split", "agree": 0, "voters": 0, "binding": False}
    top, n = Counter(votes.values()).most_common(1)[0]
    tier = "unanimous" if n == len(votes) and len(votes) > 1 else "majority" if n * 2 > len(votes) else "split"
    role = top if tier != "split" else "UNCLEAR"
    return {"role": role, "tier": tier, "agree": n, "voters": len(votes), "binding": role in BINDING}


def pairwise_kappa(a: Sequence[str], b: Sequence[str]) -> float:
    """Cohen's kappa between two voters' roles on the same ids."""
    n = len(a)
    if n == 0:
        return float("nan")
    po = sum(x == y for x, y in zip(a, b, strict=True)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[r] * cb[r] for r in set(ca) | set(cb)) / (n * n)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)
