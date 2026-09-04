# AriadneThread

Real-time fraud ring detection system for Razorpay's AI Buildathon (Track 02 — AI Risk Manager).

Builds a live transaction graph, detects coordinated communities, and scores them using seven explainable signals across 12 fraud typologies. Includes an ML-powered Chargeback Evidence Responder for automated dispute management.

> 100% synthetic data. No real transactions, users, or PII. Defense-only.

---

## Architecture

```
┌──────────────┐    WebSocket     ┌───────────────────┐
│  Next.js      │◄───────────────►│  FastAPI Backend   │
│  Frontend     │    REST API     │                    │
│  :3000        │                 │  Graph Engine      │
└──────────────┘                 │  Detection (7 sig) │
                                  │  ML Predictor      │
                                  │  Chargeback Engine  │
                                  │  AI Explainer       │
                                  └───────────────────┘
```

- **Graph Engine** — NetworkX-based transaction graph with real-time updates
- **Detection** — Community detection with 7 explainable signals
- **Fairness Audit** — Blast radius analysis and cohort-level metrics
- **ML Predictor** — XGBoost chargeback risk scoring
- **Chargeback Engine** — Evidence collection, prioritization, response generation
- **AI Explainer** — Gemini/OpenAI-powered ring explanations

---

## Quickstart

### Docker

```bash
git clone https://github.com/GowsiSM/AriadneThread.git
cd AriadneThread
docker compose up --build
```

### Manual

**Backend:**

```bash
cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000.

---

## Environment Variables

| Variable                  | Default                    | Description                           |
| ------------------------- | -------------------------- | ------------------------------------- |
| `GEMINI_API_KEY`          | —                          | Google Gemini key for AI explanations |
| `AI_API_KEY`              | —                          | OpenAI-compatible fallback            |
| `AI_MODEL`                | `gpt-4o-mini`              | Model for AI explanations             |
| `DATABASE_PATH`           | `./data/fraud_sentinel.db` | SQLite file path                      |
| `STREAM_TPS`              | `15`                       | Transactions per second               |
| `DETECTION_EVERY_N_EDGES` | `30`                       | Detection re-run cadence              |
| `FRONTEND_ORIGIN`         | `http://localhost:3000`    | CORS origin                           |

See [backend/.env.example](backend/.env.example) for full details.

---

## API Endpoints

### Core

| Method | Path                  | Description                  |
| ------ | --------------------- | ---------------------------- |
| GET    | `/api/health`         | Health check                 |
| WS     | `/ws/stream`          | Real-time transaction stream |
| POST   | `/api/stream/restart` | Replay dataset               |

### Detection

| Method | Path              | Description                |
| ------ | ----------------- | -------------------------- |
| GET    | `/api/rings`      | Detected rings             |
| GET    | `/api/metrics`    | Precision, recall, F1      |
| GET    | `/api/evaluation` | Threshold sweep + fairness |

### Investigation

| Method | Path                     | Description  |
| ------ | ------------------------ | ------------ |
| GET    | `/api/cases`             | List cases   |
| GET    | `/api/cases/{id}`        | Case details |
| POST   | `/api/cases/{id}/events` | Add event    |

### Chargeback

| Method | Path                            | Description          |
| ------ | ------------------------------- | -------------------- |
| GET    | `/api/chargeback/cases`         | List cases           |
| POST   | `/api/chargeback/cases`         | Create case          |
| GET    | `/api/chargeback/evidence/{id}` | Prioritized evidence |
| GET    | `/api/chargeback/response/{id}` | Response package     |

---

## Detection Signals

| Signal               | Measures                             |
| -------------------- | ------------------------------------ |
| Cycle involvement    | Circular transaction patterns        |
| Community isolation  | Separation from legitimate traffic   |
| PageRank anomaly     | Unusual graph centrality             |
| Temporal burst       | Concentrated activity windows        |
| Neighbor propagation | Risk from connected flagged users    |
| Motif presence       | Known fraud subgraph patterns        |
| Flow concentration   | Money funneling through single nodes |

---

## Performance

Live 12-typology dataset (385 users, 1282 transactions):

| Threshold        | Precision | Recall   | F1       |
| ---------------- | --------- | -------- | -------- |
| 30               | 0.24      | 1.00     | 0.39     |
| 35               | 0.27      | 0.65     | 0.38     |
| **40 (default)** | **1.00**  | **0.47** | **0.64** |
| 45               | 1.00      | 0.22     | 0.37     |

Default threshold is 40 — highest recall with perfect precision. Full sweep at `GET /api/evaluation`.

---

## Project Structure

```
fraud-ring-sentinel/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI application
│   │   ├── synthetic.py         # 12-typology dataset generator
│   │   ├── detection.py         # Ring detection engine
│   │   ├── graph_engine.py      # NetworkX graph operations
│   │   ├── fairness.py          # Fairness audit + blast radius
│   │   ├── evaluation.py        # Threshold sweep + metrics
│   │   ├── ai_explainer.py      # Gemini/OpenAI explanations
│   │   ├── ml/                  # Chargeback ML predictor
│   │   └── chargeback/          # Evidence engine + response gen
│   ├── tests/                   # 144 tests
│   └── requirements.txt
├── frontend/
│   ├── components/
│   │   ├── GraphAnalysisView.tsx
│   │   ├── GraphView.tsx
│   │   └── pages/
│   └── lib/types.ts
├── data/
├── models/
├── scripts/
└── docker-compose.yml
```

---

## Live Stream Notes

The backend streams 1282 transactions over WebSocket (`/ws/stream`) once at startup.

- Stream completes in ~10 seconds at 15 TPS
- Click **Restart** in the header (or `POST /api/stream/restart`) to replay
- Late connections receive the latest snapshot
- Set `STREAM_TPS=3` to slow down for demos

---

## License

MIT
