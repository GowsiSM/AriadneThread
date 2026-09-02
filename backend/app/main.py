from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import asdict

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from . import data_gen, db
from .ai_explainer import explain_ring
from .detection import run_detection, RingCandidate
from .fairness import compute_cohort_fp_stats, compute_blast_radius, precision_recall
from .graph_engine import TransactionGraph
from .websocket_manager import ConnectionManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("fraud_sentinel")

SCORE_THRESHOLD = 55.0
DETECTION_EVERY_N_EDGES = int(os.getenv("DETECTION_EVERY_N_EDGES", "30"))
STREAM_TPS = float(os.getenv("STREAM_TPS", "15"))
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")

app = FastAPI(title="Fraud Ring Sentinel API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN, "*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

manager = ConnectionManager()

# ---- global in-process state (fine for an MVP single-worker demo) ----
users, transactions = data_gen.generate_dataset()
user_index = {u.user_id: u for u in users}
tx_graph = TransactionGraph()
latest_candidates: list[RingCandidate] = []
latest_metrics: dict = {}
latest_fairness: dict = {}
tx_value_by_user: dict[str, float] = {}
stream_stats = {"emitted": 0, "total": len(transactions), "started": False, "done": False}


def _candidate_to_dict(c: RingCandidate) -> dict:
    return {
        "ring_id": c.ring_id,
        "members": c.members,
        "score": c.score,
        "signals": [asdict(s) for s in c.signals],
        "key_edges": c.key_edges,
    }


async def _run_detection_and_broadcast():
    global latest_candidates, latest_metrics, latest_fairness
    directed = tx_graph.snapshot()
    shared = tx_graph.shared_attribute_graph(user_index)
    try:
        candidates = run_detection(directed, shared, score_threshold=SCORE_THRESHOLD)
    except Exception as exc:
        logger.error("Detection run failed, keeping previous results: %s", exc)
        db.log_audit("detection_error", {"error": str(exc)})
        return

    latest_candidates = candidates
    latest_metrics = precision_recall(candidates, user_index, SCORE_THRESHOLD)
    latest_fairness = {
        "cohorts": [asdict(s) for s in compute_cohort_fp_stats(
            candidates, user_index, SCORE_THRESHOLD, {}
        )]
    }
    db.log_audit("detection_run", {"n_candidates": len(candidates), "metrics": latest_metrics})

    flagged = [c for c in candidates if c.score >= SCORE_THRESHOLD][:5]
    for cand in flagged:
        cd = _candidate_to_dict(cand)
        explanation = await explain_ring(cd)
        blast = compute_blast_radius(cand, user_index, tx_value_by_user)
        blast_d = asdict(blast)
        db.save_ring(cd, explanation, blast_d)
        db.log_audit("ring_flagged", {"ring_id": cand.ring_id, "score": cand.score})
        await manager.broadcast({
            "type": "ring_alert",
            "ring": cd,
            "explanation": explanation,
            "blast_radius": blast_d,
        })

    await manager.broadcast({
        "type": "metrics_update",
        "metrics": latest_metrics,
        "fairness": latest_fairness,
        "stream": stream_stats,
    })


async def _streamer():
    stream_stats["started"] = True
    delay = 1.0 / max(STREAM_TPS, 0.1)
    for tx in transactions:
        tx_graph.add_transaction(tx)
        tx_value_by_user[tx.sender] = tx_value_by_user.get(tx.sender, 0.0) + tx.amount
        tx_value_by_user[tx.receiver] = tx_value_by_user.get(tx.receiver, 0.0) + tx.amount
        stream_stats["emitted"] += 1

        await manager.broadcast({
            "type": "transaction",
            "tx": tx.to_dict(),
        })

        if tx_graph.edge_count % DETECTION_EVERY_N_EDGES == 0:
            await _run_detection_and_broadcast()

        await asyncio.sleep(delay)

    await _run_detection_and_broadcast()
    stream_stats["done"] = True
    await manager.broadcast({"type": "stream_complete", "stream": stream_stats})
    db.log_audit("stream_complete", stream_stats)


@app.on_event("startup")
async def startup():
    db.log_audit("startup", {"n_users": len(users), "n_transactions": len(transactions)})
    asyncio.create_task(_streamer())


@app.get("/api/health")
async def health():
    return {"status": "ok", "stream": stream_stats}


@app.get("/api/rings")
async def get_rings():
    return {"rings": [_candidate_to_dict(c) for c in latest_candidates], "threshold": SCORE_THRESHOLD}


@app.get("/api/rings/{ring_id}")
async def get_ring(ring_id: str):
    for c in latest_candidates:
        if c.ring_id == ring_id:
            cd = _candidate_to_dict(c)
            explanation = await explain_ring(cd)
            blast = compute_blast_radius(c, user_index, tx_value_by_user)
            return {"ring": cd, "explanation": explanation, "blast_radius": asdict(blast)}
    return {"error": "not found"}


@app.get("/api/metrics")
async def get_metrics():
    return {"metrics": latest_metrics, "stream": stream_stats}


@app.get("/api/fairness")
async def get_fairness():
    return latest_fairness


@app.get("/api/users/{user_id}")
async def get_user(user_id: str):
    u = user_index.get(user_id)
    if not u:
        return {"error": "not found"}
    return asdict(u)


@app.websocket("/ws/stream")
async def ws_stream(ws: WebSocket):
    await manager.connect(ws)
    try:
        # snapshot so a reconnecting client isn't left guessing what it missed
        await ws.send_json({
            "type": "snapshot",
            "rings": [_candidate_to_dict(c) for c in latest_candidates],
            "metrics": latest_metrics,
            "fairness": latest_fairness,
            "stream": stream_stats,
        })
        while True:
            # We don't expect inbound messages, but keep the loop alive so
            # we detect disconnects promptly.
            await ws.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(ws)
    except Exception as exc:
        logger.warning("ws loop ended: %s", exc)
        await manager.disconnect(ws)
