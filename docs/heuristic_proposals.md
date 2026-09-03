# Heuristic proposals — AI-assisted design, human-curated implementation

This is the one place in the project where AI touched *design*, not just
runtime explanation, and it happened offline before any code was written —
the pipeline itself never calls an LLM to pick or tune a detection rule.

## What we did

We described the available graph features (per-user account age, device/IP
sharing, transaction timing, direction, amount) to an LLM and asked for
candidate ring-detection heuristics. It proposed 9. We kept 4, rejected 5,
and hard-coded the kept ones as plain Python functions in `detection.py`.

## Proposed (paraphrased from the design session)

| # | Heuristic | Kept? | Why |
|---|-----------|-------|-----|
| 1 | Flag accounts that transact only with each other in a closed loop within a short window | ✅ | Became `cycle_involvement` — a real, well-known layering signature and cheap to compute deterministically with `nx.simple_cycles`. |
| 2 | Flag dense subgraphs with few external connections | ✅ | Became `community_isolation` — directly operationalizes "acting as a coordinated group, not individuals." |
| 3 | Flag accounts receiving disproportionate inbound value vs. the rest of the network | ✅ | Became `pagerank_anomaly` — PageRank on the transaction graph is a standard way to surface "unusual money magnets" without needing labeled fraud data. |
| 4 | Flag a large single inflow followed by fast fan-out to many recipients | ✅ | Became `temporal_burst` — the classic mule-network signature (collect, then disperse before it can be clawed back). |
| 5 | Flag any account whose device ID appears on more than one account | ❌ | Too noisy — legitimate shared-device cases (family members, shared office kiosks) dominate at low thresholds. We fold this into the *shared-attribute graph* used to seed community detection instead of scoring it directly. |
| 6 | Use account age alone as a fraud score component | ❌ | Directly penalizes new users as a class — this is exactly the kind of blunt signal the fairness audit exists to catch. We use age only as a *cohort* label for the blast-radius report, never as a scoring input. |
| 7 | Flag high-velocity accounts (many transactions per hour) | ❌ | Redundant with `temporal_burst` once burst detection was added; kept the project to one clean signal per underlying pattern rather than three overlapping ones. |
| 8 | Use a GNN embedding similarity score between accounts | ❌ | Real technique, wrong scope for a 3-day MVP — adds a training pipeline, a model artifact, and a non-deterministic, harder-to-audit scoring path. The track's bar asks for explainable, bounded actions; a hand-auditable weighted sum of five named signals is more defensible than an embedding distance nobody can explain to a reviewer. |
| 9 | Flag accounts transacting only at night | ❌ | Interesting empirically (seen in related public projects) but not implemented in synthetic data generation used here, so it would be untestable against our own ground truth — dropped rather than shipped unverified. |

## The actual rule

**AI proposes candidate heuristics and, at runtime, explains already-computed
results in plain English. It never selects, weights, or executes a
detection rule, and it never decides whether a ring gets flagged.** All four
kept heuristics are plain, testable Python in `detection.py`, unit-tested in
`tests/test_detection.py`, with fixed weights (30/25/20/15/10) documented in
that module's docstring.
