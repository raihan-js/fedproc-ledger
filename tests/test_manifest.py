import json
import subprocess

from fedproc_ledger.manifest import config_hash, git_state, sha256_file, write_manifest


def test_config_hash_ignores_key_order_and_changes_with_values():
    assert config_hash({"a": 1, "b": [1, 2]}) == config_hash({"b": [1, 2], "a": 1})
    assert config_hash({"a": 1}) != config_hash({"a": 2})


def test_sha256_file(tmp_path):
    p = tmp_path / "x.txt"
    p.write_bytes(b"abc")
    assert sha256_file(p) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_write_manifest_records_inputs_outputs_config_and_git(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    inp, outp = tmp_path / "in.txt", tmp_path / "out.txt"
    inp.write_text("in")
    outp.write_text("out")
    m = write_manifest(
        "demo", [inp], [outp, tmp_path / "missing.txt"], {"k": 1}, tmp_path / "m" / "demo.json", repo=tmp_path
    )
    saved = json.loads((tmp_path / "m" / "demo.json").read_text())
    assert saved["step"] == "demo" and saved["config_hash"] == config_hash({"k": 1})
    assert saved["inputs"][0]["sha256"] == sha256_file(inp)
    assert saved["outputs"][1]["missing"] is True
    assert m["git"]["dirty"] is True  # the files are untracked


def test_git_state_outside_a_repo(tmp_path):
    assert git_state(tmp_path)["sha"] is None
