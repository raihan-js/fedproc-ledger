"""Paper tables (LaTeX) and the forest plot, generated from results/*.json only: release/paper/tables.tex, fig_forest.pdf."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

R = Path("results")
OUT = Path("release/paper")
OUT.mkdir(parents=True, exist_ok=True)


def ld(name: str) -> dict:
    return json.loads((R / name).read_text())


ROUNDS = {  # round -> (label, eval-file suffix for the max-q configuration)
    3: ("Round 3 (rules v1.1)", ""),
    4: ("Round 4 (rules v1.2)", ""),
    5: ("Round 5 (rules v1.2)", "_maxprim"),
    6: ("Round 6 (rules v1.3)", ""),
    7: ("Round 7 (rules v1.4, temporal)", ""),
}
ANN = [
    ("majority", "majority_binding"),
    ("agent", "agent"),
    ("gpt-4o-mini", "judge_gpt-4o-mini"),
    ("gpt-4.1-mini", "judge_gpt-4.1-mini"),
]
P0 = "paired model max q>=0.5 vs B0 (VETR)"
rows, forest = [], []
for r, (label, suf) in ROUNDS.items():
    m = ld(f"ledger_eval_round{r}_majority_binding{suf}.json")
    mod, b0 = m["model max q>=0.5"], m["B0 (VETR)"]
    p = m[P0]
    rows.append(
        f"{label} & {m['_meta']['documents']} & {m['_meta']['labelled']} & {b0['f']:.3f} & {mod['f']:.3f} & "
        f"{p['diff']:+.3f} [{p['lo']:+.3f}, {p['hi']:+.3f}] & {b0['specificity']:.2f} & {mod['specificity']:.2f} & {b0['recall']:.3f} & {mod['recall']:.3f} \\\\"
    )
    for name, key in ANN:
        d = ld(f"ledger_eval_round{r}_{key}{suf}.json")[P0]
        forest.append((f"R{r} {name}", d["diff"], d["lo"], d["hi"]))
tab = (
    "\\begin{tabular}{lrrrrrrrrr}\n\\toprule\n"
    "Test & Docs & Nums & F1 B0 & F1 model & $\\Delta$F1 [95\\% CI] & Spec B0 & Spec model & Rec B0 & Rec model \\\\\n\\midrule\n"
    + "\n".join(rows)
    + "\n\\bottomrule\n\\end{tabular}\n"
)
(OUT / "tab_fresh.tex").write_text(tab)
c = ld("annotator_ceiling.json")
lines = ["\\begin{tabular}{lrrr}\n\\toprule\nPair & Items & Agreement & Cohen $\\kappa$ \\\\\n\\midrule"]
for k, v in c["pairs"].items():
    lines.append(
        f"{k.replace('~', ' vs ').replace('g4o', 'gpt-4o-mini').replace('g41', 'gpt-4.1-mini')} & {v['n']} & {v['accuracy']:.3f} & {v['kappa']:.2f} \\\\"
    )
lines.append("\\midrule")
for k, v in c["model_vs"].items():
    lines.append(
        f"model vs {k.replace('g4o', 'gpt-4o-mini').replace('g41', 'gpt-4.1-mini')} & {v['n']} & {v['accuracy']:.3f} & {v['kappa']:.2f} \\\\"
    )
lines.append("\\bottomrule\n\\end{tabular}\n")
(OUT / "tab_ceiling.tex").write_text("\n".join(lines))
fig, ax = plt.subplots(figsize=(6.4, 7.5))
for i, (_lab, d, lo, hi) in enumerate(reversed(forest)):
    ax.plot([lo, hi], [i, i], color="#1f77b4", lw=1.6)
    ax.plot([d], [i], "o", color="#1f77b4", ms=4)
ax.axvline(0, color="#555", lw=0.8, ls="--")
ax.set_yticks(range(len(forest)))
ax.set_yticklabels([f[0] for f in reversed(forest)], fontsize=7)
ax.set_xlabel("F1 difference, model minus status-quo regexes (95% cluster bootstrap)")
fig.tight_layout()
fig.savefig(OUT / "fig_forest.pdf")
print((OUT / "tab_fresh.tex").read_text())
print((OUT / "tab_ceiling.tex").read_text())
