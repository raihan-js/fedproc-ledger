from typer.testing import CliRunner

from fedproc_ledger.cli import PHASES, app

runner = CliRunner()


def test_help_lists_every_step():
    out = runner.invoke(app, ["--help"]).output
    for name, _phase, _desc in PHASES:
        assert name in out
    assert "env" in out and "phases" in out


def test_env_runs_without_torch_or_gpu():
    r = runner.invoke(app, ["env"])
    assert r.exit_code == 0
    assert "fedproc-ledger" in r.output and "python" in r.output


def test_env_json_is_valid():
    import json

    r = runner.invoke(app, ["env", "--json"])
    assert r.exit_code == 0
    assert set(json.loads(r.output)) >= {"python", "torch", "cuda_available", "gpu"}


def test_unbuilt_steps_exit_nonzero_with_a_pointer_to_the_plan():
    r = runner.invoke(app, ["registry"])
    assert r.exit_code == 2


def test_acquire_is_a_command_group():
    r = runner.invoke(app, ["acquire", "--help"])
    assert r.exit_code == 0 and "probe" in r.output
