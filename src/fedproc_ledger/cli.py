"""`fl`: one subcommand per pipeline step. Steps read and write files under data/ and results/ and write a manifest."""

from __future__ import annotations

import json

import typer

from fedproc_ledger import __version__
from fedproc_ledger.envinfo import environment, gpu_line

app = typer.Typer(
    help="fedproc-ledger: which clauses actually bind a US federal solicitation, and how.",
    no_args_is_help=True,
    add_completion=False,
)

# (command, phase, one-line help). Only `env` and `phases` exist in Phase 0;
# the rest are placeholders so the CLI shape is fixed from day one.
PHASES: list[tuple[str, int, str]] = [
    ("acquire", 1, "Search GovCon API, download attachments, apply the legal/privacy filter."),
    ("registry", 2, "Build the eCFR clause registry with version history (and the deviations table)."),
    ("extract", 3, "Layout-aware text extraction with explicit checkbox markers."),
    ("candidates", 4, "Generate clause-number candidates and tag document sections."),
    ("rules", 4, "Run the rules baseline (B1) and the VETR status-quo baseline (B0)."),
    ("annotate", 5, "Streamlit annotation tool."),
    ("pilot", 5, "Pilot report and go/no-go numbers."),
    ("split", 6, "Build and freeze the splits, write hashes."),
    ("silver", 7, "Silver labels from rules and an LLM labeler (asks before spending)."),
    ("train", 8, "Train the span classifier."),
    ("export", 8, "ONNX export, int8 quantisation, parity and latency."),
    ("evaluate", 9, "Evaluate on dev; `--final` reads the frozen test splits exactly once."),
    ("currency", 9, "Version currency check against eCFR history."),
    ("report", 9, "Generate every table and figure from results/*.json."),
    ("ledger", 11, "Build a ledger for one document."),
    ("serve", 11, "Local FastAPI sidecar."),
]


@app.command()
def env(as_json: bool = typer.Option(False, "--json", help="Print the environment as JSON.")) -> None:
    """Print Python, torch and GPU details (the line recorded in docs/decisions.md)."""
    info = environment()
    typer.echo(
        json.dumps(info, indent=1)
        if as_json
        else f"fedproc-ledger {__version__} | python {info['python']} | {gpu_line(info)}"
    )


@app.command()
def phases() -> None:
    """List every pipeline step and the phase that implements it."""
    for name, phase, desc in PHASES:
        typer.echo(f"phase {phase:>2}  fl {name:<11} {desc}")


def _placeholder(name: str, phase: int) -> None:
    typer.echo(
        f"`fl {name}` is implemented in phase {phase} (see docs/EXECUTION_PLAN.md); nothing to run yet.", err=True
    )
    raise typer.Exit(code=2)


def _register(name: str, phase: int, desc: str) -> None:
    def command() -> None:
        _placeholder(name, phase)

    command.__name__ = name
    command.__doc__ = f"[phase {phase}, not implemented yet] {desc}"
    app.command(name)(command)


for _name, _phase, _desc in PHASES:
    _register(_name, _phase, _desc)


if __name__ == "__main__":
    app()
