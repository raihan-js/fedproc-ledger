# Training roadmap: what actually moves the score (2026-10-07)

## Where the score stands
Four consecutive fresh pre-registered wins over the status-quo regexes (+0.14, +0.10, +0.11, +0.08 F1), specificity 70-79% vs 8-19%, recall 0.90-0.94. The measurable ceiling against judge-majority labels is set by annotator agreement (75-82%), not by model capacity — so the next gains must come from (a) a model that reads language the rules cannot, and (b) better labels, in that order.

## Next model: ModernBERT span classifier (plan Phase 8, never built)
The shipped model is one-vs-rest logistic regression on 60 hand features + char TF-IDF. The queued design: `answerdotai/ModernBERT-base` over layout-marked windows (2,048 tokens, stride half), candidate = mean token embeddings + line mean, 2-layer MLP over the 10 roles, class-weighted cross-entropy, silver pretraining then gold fine-tune. Fits the RTX 3060 12 GB with bf16 + gradient checkpointing (batch 1, accumulation 16).
Protocol (no shortcuts): train on rounds-2-7 agent labels + 2,663 mention labels grouped by solicitation/agency (templates leak across documents); model-select on frozen dev; claim nothing until a fresh round 8. Ablations A1-A7 from the plan still apply (layout markers on/off is the key one: it quantifies what VETR's Smalot-based text loses).

## Why not reinforcement learning
RL needs a reward signal. There is none: no expert preference data, no user clicks, and the task is classification with a fixed schema, not generation. The current errors are document-structure problems (spec narrative, lost markers, mid-line exclusions) that supervised span classification addresses directly. RL becomes worth discussing only if (1) reviewers produce preference data ("this ledger is better than that one") or (2) the task grows a generative head (evidence-span selection). Until then RL would inherit the same 75-82% annotator ceiling while adding variance. Say this in public, not "we use RL".

## Label leverage (bigger than model leverage right now)
- VETR reviewer gold (~200 documents): the one independent check; unblocks customer-visible use.
- More contexts per number for judges (they misread checklists from 3-line windows).
- Applicable/R mode: referenced requirements are where B0 still wins; a second head for them turns a loss (-0.03 applicable) into coverage.
- Mid-line exclusion wording (found in round 7 labelling): one regex, one test, fresh round 8.

## Guardrails
Never tune on test; every weight/rule change needs a fresh round; cluster-bootstrap intervals on every claim; negative results stay in the log.
