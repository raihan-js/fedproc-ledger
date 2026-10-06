import json

import pytest

from fedproc_ledger.label import panel as P

ITEMS = [
    {"id": "d-p1-0", "number": "52.204-21", "breadcrumb": ["SECTION I"], "context": "a >>>52.204-21<<< b"},
    {"id": "d-p1-1", "number": "52.219-9", "breadcrumb": [], "context": "x", "alternate": "Alternate II"},
]


def test_prompt_lists_ids_headings_and_changes_with_variant():
    a = P.build_prompt(ITEMS, P.Voter("a", "m", "A"))
    b = P.build_prompt(ITEMS, P.Voter("b", "m", "B"))
    assert "id=d-p1-0 number=52.204-21" in a[1]["content"] and "headings: SECTION I" in a[1]["content"]
    assert "(no heading seen)" in a[1]["content"] and "[alternate: Alternate II]" in a[1]["content"]
    assert a[0]["content"] != b[0]["content"] and b[0]["content"].startswith("Task:")
    la = [x for x in a[0]["content"].split("\n") if x.split(":")[0] in P.LLM_ROLES]
    lb = [x for x in b[0]["content"].split("\n") if x.split(":")[0] in P.LLM_ROLES]
    assert len(la) == 10 and sorted(la) == sorted(lb) and la != lb  # same roles, other order


def test_context_marks_the_candidate_and_survives_missing_raw():
    lines = ["h1", "", "see 52.204-21 now", "tail"]
    assert ">>>52.204-21<<<" in P.context_text(lines, 2, "52.204-21")
    assert ">>> see 52.204-21 now <<<" in P.context_text(lines, 2, "52-204")


def test_parse_drops_unknown_ids_roles_and_bad_json():
    ok = json.dumps(
        {"labels": [{"id": "a", "role": "FULL_TEXT"}, {"id": "zz", "role": "FULL_TEXT"}, {"id": "b", "role": "MAYBE"}]}
    )
    assert P.parse_labels(ok, ["a", "b"]) == {"a": "FULL_TEXT"}
    assert P.parse_labels("not json", ["a"]) == {} and P.parse_labels("[1]", ["a"]) == {}


def test_vote_chunks_caches_and_retries_missing_ids(tmp_path):
    items = [{"id": f"i{k}", "number": "52.1-1", "breadcrumb": [], "context": "c"} for k in range(12)]
    calls = []

    def chat(model, msgs):
        calls.append(len(msgs[1]["content"]))
        ids = [x for x in (f"i{k}" for k in range(12)) if f"id={x} " in msgs[1]["content"]]
        if len(ids) == 10:
            ids = ids[:-1]  # the model skips one id in a full chunk
        return json.dumps({"labels": [{"id": i, "role": "INCORPORATED_BY_REFERENCE"} for i in ids]})

    cache = P.Cache(tmp_path / "c.jsonl")
    out = P.vote(items, P.Voter("a", "m"), chat, cache)
    assert len(out) == 12 and len(calls) == 3  # 2 chunks + 1 retry
    n = len(calls)
    assert (
        P.vote(items, P.Voter("a", "m"), chat, P.Cache(tmp_path / "c.jsonl")) == out and len(calls) == n
    )  # all cached


def test_adjudication_tiers_and_binding():
    assert P.adjudicate({"a": "FULL_TEXT", "b": "FULL_TEXT", "c": "FULL_TEXT"})["tier"] == "unanimous"
    m = P.adjudicate(
        {"a": "FULL_TEXT", "b": "FULL_TEXT", "c": "NARRATIVE_MENTION", "d": "NARRATIVE_MENTION", "e": "FULL_TEXT"}
    )
    assert (m["role"], m["tier"], m["binding"]) == ("FULL_TEXT", "majority", True)
    s = P.adjudicate({"a": "FULL_TEXT", "b": "NARRATIVE_MENTION"})
    assert (s["role"], s["tier"], s["binding"]) == ("UNCLEAR", "split", False)
    assert P.adjudicate({})["tier"] == "split"


def test_kappa_perfect_chance_and_empty():
    a = ["x", "y", "x", "y"]
    assert P.pairwise_kappa(a, a) == 1.0
    assert P.pairwise_kappa(a, ["x", "x", "y", "y"]) == pytest.approx(0.0, abs=1e-9)  # agreement at chance level
    assert P.pairwise_kappa(["x", "x"], ["x", "x"]) == 1.0
    assert P.pairwise_kappa([], []) != P.pairwise_kappa([], [])  # nan


def test_chunks_respect_count_and_size():
    small = [{"id": str(i), "context": "x" * 10} for i in range(25)]
    assert [len(c) for c in P.chunks(small)] == [10, 10, 5]
    big = [{"id": str(i), "context": "x" * 4000} for i in range(5)]
    assert [len(c) for c in P.chunks(big)] == [2, 2, 1]
    assert P.chunks([]) == []
