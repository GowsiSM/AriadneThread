# 🛡️ AriadneThread

A **defense-only, real-time fraud-ring detector** built for Razorpay's AI Buildathon (Track 02 — AI Risk Manager).

Instead of scoring transactions individually, it builds a live transaction graph, detects coordinated communities, and scores them using seven explainable signals (cycle involvement, community isolation, PageRank anomaly, temporal burst, neighbor propagation, motif presence, flow concentration) across 12 fraud typologies.

> ⚠️ **100% synthetic data** — no real transactions, users, or PII. Defense-only — no blocking or charging logic.

---

## 📊 Honest metrics (live, 12-typology dataset)

Measured against the actual dataset streaming through the live app (`/api/metrics`, seed 42, 385 users, 1282 transactions), not a separately-generated sample:

| Threshold                | Precision | Recall   | F1       |
| ------------------------ | --------- | -------- | -------- |
| 30                       | 0.24      | 1.00     | 0.39     |
| 35                       | 0.27      | 0.65     | 0.38     |
| **40 (shipped default)** | **1.00**  | **0.47** | **0.64** |
| 45                       | 1.00      | 0.22     | 0.37     |
| 55 (old, stale default)  | 1.00      | 0.06     | 0.11     |

We ship **40** — the highest-recall point that still holds perfect precision — because a false positive is exactly what the fairness/blast-radius audit exists to make expensive, not something to trade away for a better-looking recall number. Full sweep is live at `GET /api/evaluation`.

**What broke along the way, briefly:** the 12-typology generator (`synthetic.py`) was fully built and unit-tested but never wired into `main.py`'s live stream — the dashboard was silently still running the old 3-typology dataset. After fixing that, the evaluation endpoint _also_ turned out to be generating its own separate dataset with a different seed/scale than the live one, so an initial threshold pick (35) looked great in isolation (P=1.00, R=0.75) but measured P=0.27, R=0.65 once actually deployed. Fixed by making `/api/evaluation` reuse the exact in-memory dataset the live stream runs on, so the sweep and the dashboard can never disagree again.

---

## 🚀 Quickstart

### Docker (recommended)

```bash
git clone https://github.com/GowsiSM/AriadneThread.git
cd AriadneThread
docker compose up --build
```

---

## 📡 Live stream & demo notes

The backend streams the full 1282-transaction dataset over a WebSocket
(`/ws/stream`) **once at startup**, then marks the stream as complete. The
live graph and Transactions page render whatever transactions arrive while
the frontend is connected.

- **Stream timing:** the stream completes in roughly **10 seconds** at the
  default rate (1282 tx at 15 TPS). The frontend must be open **during that
  window** to watch it live.
- **Missed the stream?** No problem — click the **↻ Restart stream** button
  in the header (or call `POST /api/stream/restart`) to replay the dataset
  from the beginning without restarting the backend. The graph and
  Transactions page will repopulate as the replay streams.
- **Late connection:** even if you connect after the stream finishes, the
  snapshot includes the most recent transactions, so the graph and
  Transactions page are never empty.
- **Slow it down for a demo:** set `STREAM_TPS` (e.g. `STREAM_TPS=3`) to
  stretch the stream out so it's easier to watch live. `DETECTION_EVERY_N_EDGES`
  controls how often detection re-runs during the stream.
- **Health check:** `GET /health` (alias of `GET /api/health`) returns
  `{"status": "ok", "stream": {...}}`.
