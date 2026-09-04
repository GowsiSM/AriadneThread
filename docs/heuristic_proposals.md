# Heuristic Proposals

AI-assisted design, human-curated implementation. This is the one place in
the project where AI touched *design* — and it happened offline before any
code was written. The pipeline itself never calls an LLM to pick or tune a
detection rule.

## What we did

We described the available graph features (per-user account age, device/IP
sharing, transaction timing, direction, amount) to an LLM and asked for
candidate ring-detection heuristics. It proposed 9. We kept 4, rejected 5,
and hard-coded the kept ones as plain Python functions in `detection.py`.

## Proposed

| # | Heuristic | Kept? | Why |
|---|---|---|---|
| 1 | Flag accounts that transact only with each other in a closed loop within a short window | Yes | Became `cycle_involvement` — a well-known layering signature, cheap to compute with `nx.simple_cycles` |
| 2 | Flag dense subgraphs with few external connections | Yes | Became `community_isolation` — operationalizes "acting as a coordinated group" |
| 3 | Flag accounts receiving disproportionate inbound value | Yes | Became `pagerank_anomaly` — surfaces "unusual money magnets" without labeled data |
| 4 | Flag a large single inflow followed by fast fan-out | Yes | Became `temporal_burst` — the classic mule-network signature |
| 5 | Flag any account whose device ID appears on more than one account | No | Too noisy — legitimate shared-device cases dominate. Folded into the shared-attribute graph instead of scored directly |
| 6 | Use account age alone as a fraud score component | No | Directly penalizes new users as a class — exactly what the fairness audit exists to catch. Age is used only as a cohort label |
| 7 | Flag high-velocity accounts (many transactions per hour) | No | Redundant with `temporal_burst` |
| 8 | Use a GNN embedding similarity score between accounts | No | Real technique, wrong scope — adds a training pipeline and a non-deterministic, harder-to-audit scoring path |
| 9 | Flag accounts transacting only at night | No | Not implemented in synthetic data generation, so untestable against our own ground truth |

## The actual rule

**AI proposes candidate heuristics and, at runtime, explains already-computed
results in plain English. It never selects, weights, or executes a detection
rule, and it never decides whether a ring gets flagged.** All four kept
heuristics are plain, testable Python in `detection.py`, unit-tested in
`tests/test_detection.py`, with fixed weights documented in that module's
docstring.
