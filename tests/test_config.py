from fedproc_ledger.config import load_config


def test_load_config_adds_a_stable_hash(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text('name = "x"\nn = 3\n')
    a, b = load_config(p), load_config(p)
    assert a["name"] == "x" and a["n"] == 3 and a["_hash"] == b["_hash"]
    p.write_text('name = "x"\nn = 4\n')
    assert load_config(p)["_hash"] != a["_hash"]
