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
from .investigation import CaseManager, CaseStatus, auto_create_cases
from .versions import DETECTOR_VERSION, DATASET_VERSION, RUN_VERSION, log_versions
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
case_manager = CaseManager()

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
    d = {
        "ring_id": c.ring_id,
        "members": c.members,
        "score": c.score,
        "signals": [asdict(s) for s in c.signals],
        "key_edges": c.key_edges,
    }
    # --- Stage 3: graph intelligence fields ---
    if c.typology is not None:
        d["typology"] = c.typology
        d["typology_confidence"] = c.typology_confidence
    if c.roles:
        d["roles"] = [asdict(r) for r in c.roles]
    if c.flow_summary is not None:
        fs = c.flow_summary
        d["flow_summary"] = {
            "total_inflow": fs.total_inflow,
            "total_outflow": fs.total_outflow,
            "internal_volume": fs.internal_volume,
            "external_volume": fs.external_volume,
            "net_flow": fs.net_flow,
            "flow_ratio": fs.flow_ratio,
            "dominant_path": list(fs.dominant_path),
            "dominant_amount": fs.dominant_amount,
            "concentration": fs.concentration,
        }
    if c.motifs:
        d["motifs"] = [
            {"motif_type": m.motif_type, "nodes": list(m.nodes), "evidence": m.evidence, "confidence": m.confidence}
            for m in c.motifs
        ]
    if c.sub_rings:
        d["sub_rings"] = [
            {"sub_ring_id": s.sub_ring_id, "members": s.members, "reason": s.reason, "risk_contribution": s.risk_contribution}
            for s in c.sub_rings
        ]
    return d


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
        db.log_audit("ring_flagged", {
            "ring_id": cand.ring_id, "score": cand.score,
            "detector_version": DETECTOR_VERSION.hash,
        }, ring_id=cand.ring_id)
        await manager.broadcast({
            "type": "ring_alert",
            "ring": cd,
            "explanation": explanation,
            "blast_radius": blast_d,
        })

    # --- Stage 5: auto-create investigation cases ---
    new_cases = auto_create_cases(
        case_manager, candidates,
        score_threshold=SCORE_THRESHOLD,
        detector_version=DETECTOR_VERSION.hash,
        dataset_version=DATASET_VERSION.hash,
    )
    for case in new_cases:
        db.save_case(case.to_dict(), [db._serialize_event(e) for e in case.events])
        db.log_audit("case_created" if len(case.events) == 1 else "case_updated", {
            "case_id": case.case_id,
            "ring_id": case.ring_id,
            "status": case.status.value,
            "priority": case.priority.value,
        }, case_id=case.case_id, ring_id=case.ring_id)

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


# ---------------------------------------------------------------------------
# Stage 5: Investigation endpoints
# ---------------------------------------------------------------------------

@app.get("/api/cases")
async def get_cases(status: str | None = None):
    """List investigation cases, optionally filtered by status."""
    if status:
        try:
            status_enum = CaseStatus(status)
        except ValueError:
            return {"error": f"invalid status: {status}", "valid": [s.value for s in CaseStatus]}
        cases = case_manager.list_cases(status=status_enum)
    else:
        cases = case_manager.list_cases()
    return {"cases": [c.to_dict() for c in cases], "summary": case_manager.summary()}


@app.get("/api/cases/{case_id}")
async def get_case(case_id: str):
    """Get a single case with its full timeline."""
    case = case_manager.get_case(case_id)
    if not case:
        return {"error": "not found"}
    result = case.to_dict()
    result["timeline"] = case_manager.get_timeline(case_id)
    result["evidence"] = case.evidence
    result["notes"] = case.notes
    return {"case": result}


@app.post("/api/cases/{case_id}/transition")
async def transition_case(case_id: str, body: dict):
    """Transition a case to a new status. Body: {"to_status": "...", "actor": "..."}"""
    to_status_raw = body.get("to_status")
    actor = body.get("actor", "analyst")
    if not to_status_raw:
        return {"error": "to_status is required"}
    try:
        to_status = CaseStatus(to_status_raw)
    except ValueError:
        return {"error": f"invalid status: {to_status_raw}", "valid": [s.value for s in CaseStatus]}

    try:
        case = case_manager.transition(case_id, to_status, actor=actor)
    except KeyError:
        return {"error": "case not found"}
    except ValueError as exc:
        return {"error": str(exc)}

    db.save_case(case.to_dict(), [db._serialize_event(e) for e in case.events])
    db.log_audit("case_transition", {
        "case_id": case.case_id, "to_status": to_status.value, "actor": actor,
    }, case_id=case.case_id, ring_id=case.ring_id)
    return {"case": case.to_dict()}


@app.post("/api/cases/{case_id}/note")
async def add_case_note(case_id: str, body: dict):
    """Add a note to a case. Body: {"note": "...", "actor": "..."}"""
    note = body.get("note")
    actor = body.get("actor", "analyst")
    if not note:
        return {"error": "note is required"}
    try:
        event = case_manager.add_note(case_id, note, actor=actor)
    except KeyError:
        return {"error": "case not found"}

    case = case_manager.get_case(case_id)
    db.save_case(case.to_dict(), [db._serialize_event(event)])
    db.log_audit("case_note", {"case_id": case_id, "actor": actor}, case_id=case_id)
    return {"case": case.to_dict()}


@app.post("/api/cases/{case_id}/assign")
async def assign_case(case_id: str, body: dict):
    """Assign a case to an analyst. Body: {"analyst": "..."}"""
    analyst = body.get("analyst")
    if not analyst:
        return {"error": "analyst is required"}
    try:
        event = case_manager.assign(case_id, analyst)
    except KeyError:
        return {"error": "case not found"}

    case = case_manager.get_case(case_id)
    db.save_case(case.to_dict(), [db._serialize_event(event)])
    db.log_audit("case_assigned", {"case_id": case_id, "analyst": analyst}, case_id=case_id)
    return {"case": case.to_dict()}


@app.get("/api/versions")
async def get_versions():
    """Return the current detector/dataset/feature/run versions."""
    return log_versions()


@app.get("/api/evaluation")
async def get_evaluation():
    """Run full evaluation (threshold sweep + baselines + adversarial) with deterministic seed."""
    from . import data_gen as _dg
    from .graph_engine import TransactionGraph
    from .evaluation import generate_eval_report, threshold_sweep, compare_all_baselines, temporal_split_eval
    from .adversarial import run_adversarial_tests

    # Generate a fixed dataset for evaluation
    users, transactions = _dg.generate_dataset(
        n_background_users=150, n_background_tx=500, n_rings=3, seed=1,
    )
    user_index = {u.user_id: u for u in users}
    tg = TransactionGraph()
    for tx in transactions:
        tg.add_transaction(tx)

    directed_g = tg.snapshot()
    shared_attr_g = tg.shared_attribute_graph(user_index)

    # Run detection for sweep/baselines
    candidates = run_detection(directed_g, shared_attr_g, score_threshold=55.0)
    sweep = threshold_sweep(candidates, user_index)
    baselines = compare_all_baselines(directed_g, shared_attr_g, user_index)

    # Temporal split
    temporal = None
    try:
        temporal = temporal_split_eval(transactions, user_index, score_threshold=55.0)
    except Exception:
        pass

    # Adversarial robustness
    adversarial = None
    try:
        adversarial = run_adversarial_tests(seed=42, threshold=55.0)
    except Exception:
        pass

    # Serialize results
    def _to_dict(obj):
        from dataclasses import asdict as _asdict
        return _asdict(obj)

    return {
        "threshold_sweep": _to_dict(sweep),
        "baselines": [_to_dict(b) for b in baselines],
        "temporal_split": _to_dict(temporal) if temporal else None,
        "adversarial": _to_dict(adversarial) if adversarial else None,
        "current_threshold": SCORE_THRESHOLD,
        "current_rings": [_candidate_to_dict(c) for c in candidates],
        "n_users": len(user_index),
        "n_transactions": len(transactions),
    }


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
