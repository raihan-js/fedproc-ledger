"""Project paths. Everything under data/ is gitignored; results/ holds small committed JSON."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW = DATA / "raw"
INTERIM = DATA / "interim"
PROCESSED = DATA / "processed"
LABELS = DATA / "labels"
RESULTS = ROOT / "results"
CONFIGS = ROOT / "configs"
DOCS = ROOT / "docs"
