from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import asdict
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from . import synthetic, db
from .ai_explainer import explain_ring, template_explanation
from .detection import run_detection, RingCandidate
from .fairness import compute_cohort_fp_stats, compute_blast_radius, precision_recall
from .graph_engine import TransactionGraph
from .investigation import CaseManager, CaseStatus, auto_create_cases
from .versions import DETECTOR_VERSION, DATASET_VERSION, RUN_VERSION, log_versions
from .ml.predictor import MLPredictor
from .chargeback import ChargebackCaseManager, EvidenceEngine, ResponseGenerator
from .websocket_manager import ConnectionManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("fraud_sentinel")

SCORE_THRESHOLD = 40.0
# Re-tuned 2026-09-03 after wiring in the full 12-typology synthetic dataset.
#
# IMPORTANT: an earlier pass at this set SCORE_THRESHOLD=35 based on a sweep
# from /api/evaluation -- but at the time that endpoint generated its OWN
# dataset (seed=1, 200 users, 800 tx), different from the live startup
# dataset (seed=42, 300 background users -> 385 total, 1200 background tx ->
# 1282 total). Deploying threshold=35 against the REAL live dataset measured
# precision 0.27 / recall 0.65 -- nothing like the 1.00 / 0.75 the mismatched
# sweep predicted. /api/evaluation was then fixed to reuse the exact live
# dataset instead of generating a separate one (see CHANGES.md), and a fresh
# sweep against the real data shows 40 is the actual best F1 operating point
# holding perfect precision:
#   threshold=30 -> P=0.24 R=1.00 F1=0.39
#   threshold=35 -> P=0.27 R=0.65 F1=0.38
#   threshold=40 -> P=1.00 R=0.47 F1=0.64   <- selected
#   threshold=45 -> P=1.00 R=0.22 F1=0.37
#   threshold=55 (old default) -> P=1.00 R=0.06 F1=0.11
# We kept precision=1.00 as a hard constraint (a false positive is what the
# blast-radius report exists to make expensive) and picked the threshold
# that maximizes recall subject to that constraint.
DETECTION_EVERY_N_EDGES = int(os.getenv("DETECTION_EVERY_N_EDGES", "30"))
STREAM_TPS = float(os.getenv("STREAM_TPS", "15"))
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")

app = FastAPI(title="AriadneThread API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN, "*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

manager = ConnectionManager()
case_manager = CaseManager()
ml_predictor = MLPredictor()
case_manager = ChargebackCaseManager()
evidence_engine = EvidenceEngine(ml_predictor)
response_generator = ResponseGenerator()

# ---- global in-process state (fine for an MVP single-worker demo) ----
# Uses the 12-typology synthetic generator (app/synthetic.py) so the live
# stream, dashboard, and /api/rings /api/metrics /api/evaluation all reflect
# the full typology set, not just the original 3-ring baseline.
_dataset = synthetic.generate_dataset()
users, transactions = _dataset.users, _dataset.transactions
user_index = {u.user_id: u for u in users}
logger.info(
    "Loaded synthetic dataset: %d users, %d transactions, %d rings (%s)",
    len(users), len(transactions), len(_dataset.scenarios),
    ", ".join(_dataset.meta.get("typologies", [])),
)
tx_graph = TransactionGraph()
latest_candidates: list[RingCandidate] = []
latest_metrics: dict = {}
latest_fairness: dict = {}
tx_value_by_user: dict[str, float] = {}
stream_stats = {"emitted": 0, "total": len(transactions), "started": False, "done": False}
# Ring buffer of the most recent transactions so a client that connects after
# the stream finishes still has data to render (graph + transactions pages).
RECENT_TX_LIMIT = 200
recent_tx: list[dict] = []
_stream_task: asyncio.Task | None = None


def _reset_stream_state():
    """Reset all in-process stream state so a fresh replay starts clean."""
    global tx_graph, latest_candidates, latest_metrics, latest_fairness, tx_value_by_user, stream_stats, recent_tx
    tx_graph = TransactionGraph()
    latest_candidates = []
    latest_metrics = {}
    latest_fairness = {}
    tx_value_by_user = {}
    stream_stats = {"emitted": 0, "total": len(transactions), "started": False, "done": False}
    recent_tx = []


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
        # During streaming, use template explanations to avoid API calls.
        # AI explanations are generated after the stream completes.
        if stream_stats["done"]:
            explanation = await explain_ring(cd)
        else:
            explanation = template_explanation(cd)
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


async def _generate_ai_explanations():
    """Generate AI explanations for all flagged rings after the stream completes.
    
    This is called once after the entire transaction stream has been processed.
    It replaces the template explanations with AI-generated explanations and
    broadcasts the updates to connected clients.
    """
    global latest_candidates
    
    flagged = [c for c in latest_candidates if c.score >= SCORE_THRESHOLD][:5]
    if not flagged:
        return
    
    logger.info("Generating AI explanations for %d flagged rings...", len(flagged))
    db.log_audit("ai_explanation_start", {"n_rings": len(flagged)})
    
    for cand in flagged:
        cd = _candidate_to_dict(cand)
        explanation = await explain_ring(cd)
        blast = compute_blast_radius(cand, user_index, tx_value_by_user)
        blast_d = asdict(blast)
        
        # Update the stored ring with the new AI explanation
        db.save_ring(cd, explanation, blast_d)
        
        # Broadcast the updated explanation to connected clients
        await manager.broadcast({
            "type": "explanation_update",
            "ring_id": cand.ring_id,
            "explanation": explanation,
        })
        
        logger.info("AI explanation generated for ring %s (source: %s)", cand.ring_id, explanation["source"])
    
    db.log_audit("ai_explanation_complete", {"n_rings": len(flagged)})
    logger.info("AI explanation generation complete.")


async def _streamer():
    global recent_tx
    stream_stats["started"] = True
    delay = 1.0 / max(STREAM_TPS, 0.1)
    for tx in transactions:
        tx_graph.add_transaction(tx)
        tx_value_by_user[tx.sender] = tx_value_by_user.get(tx.sender, 0.0) + tx.amount
        tx_value_by_user[tx.receiver] = tx_value_by_user.get(tx.receiver, 0.0) + tx.amount
        stream_stats["emitted"] += 1
        recent_tx.append(tx.to_dict())
        if len(recent_tx) > RECENT_TX_LIMIT:
            recent_tx = recent_tx[-RECENT_TX_LIMIT:]

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
    
    # Generate AI explanations after the stream completes
    await _generate_ai_explanations()


@app.on_event("startup")
async def startup():
    global _stream_task
    db.log_audit("startup", {"n_users": len(users), "n_transactions": len(transactions)})
    _stream_task = asyncio.create_task(_streamer())


@app.get("/health")
@app.get("/api/health")
async def health():
    return {"status": "ok", "stream": stream_stats}


@app.post("/api/stream/restart")
async def restart_stream():
    """Cancel any in-flight stream and replay the dataset from scratch.

    Lets a frontend that connected after the stream finished (or wants to
    re-watch the live graph) trigger a fresh replay without restarting the
    backend process.
    """
    global _stream_task
    if _stream_task is not None and not _stream_task.done():
        _stream_task.cancel()
        try:
            await _stream_task
        except asyncio.CancelledError:
            pass
    _reset_stream_state()
    db.log_audit("stream_restart", {"n_transactions": len(transactions)})
    _stream_task = asyncio.create_task(_streamer())
    return {"status": "restarting", "stream": stream_stats}


@app.get("/api/rings")
async def get_rings():
    return {"rings": [_candidate_to_dict(c) for c in latest_candidates], "threshold": SCORE_THRESHOLD}


@app.get("/api/rings/{ring_id}")
async def get_ring(ring_id: str):
    for c in latest_candidates:
        if c.ring_id == ring_id:
            cd = _candidate_to_dict(c)
            # Use template explanation during streaming, AI explanation after stream completes
            if stream_stats["done"]:
                explanation = await explain_ring(cd)
            else:
                explanation = template_explanation(cd)
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
    """Run full evaluation (threshold sweep + baselines + adversarial) on the
    SAME dataset currently powering the live stream/dashboard -- not a
    separately-generated sample.

    Earlier this endpoint generated its own dataset with a different seed
    and scale (seed=1, 200 users, 800 tx) than the live startup dataset
    (seed=42, 300 users, 1200 tx). That mismatch produced a threshold sweep
    that looked great (precision 1.00, recall 0.75 @ threshold 35) but did
    not transfer to what was actually streaming -- the live run at
    threshold 35 measured precision 0.24, recall 0.65. Reusing the exact
    same in-memory dataset closes that gap: whatever this endpoint reports
    is, by construction, what the dashboard is showing.
    """
    from .graph_engine import TransactionGraph
    from .evaluation import generate_eval_report, threshold_sweep, compare_all_baselines, temporal_split_eval
    from .adversarial import run_adversarial_tests

    # Reuse the live dataset (module-level `users`/`transactions`/`user_index`
    # generated once at startup) rather than generating a new one.
    tg = TransactionGraph()
    for tx in transactions:
        tg.add_transaction(tx)

    directed_g = tg.snapshot()
    shared_attr_g = tg.shared_attribute_graph(user_index)

    # Run detection for sweep/baselines
    candidates = run_detection(directed_g, shared_attr_g, score_threshold=SCORE_THRESHOLD)
    sweep = threshold_sweep(candidates, user_index)
    baselines = compare_all_baselines(directed_g, shared_attr_g, user_index)

    # Temporal split
    temporal = None
    try:
        temporal = temporal_split_eval(transactions, user_index, score_threshold=SCORE_THRESHOLD)
    except Exception:
        pass

    # Adversarial robustness
    adversarial = None
    try:
        adversarial = run_adversarial_tests(seed=42, threshold=SCORE_THRESHOLD)
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


@app.post("/api/chargeback/predict")
async def predict_chargeback_risk(transaction: dict):
    return ml_predictor.predict(transaction)


@app.get("/api/chargeback/cases")
async def list_chargeback_cases(status: str | None = None):
    cases = case_manager.list_cases(status=status)
    return {"cases": cases, "total": len(cases)}


@app.get("/api/chargeback/cases/{case_id}")
async def get_chargeback_case(case_id: str):
    case = case_manager.get_case(case_id)
    if not case:
        return {"error": "case not found"}
    return case


@app.post("/api/chargeback/cases")
async def create_chargeback_case(case: dict):
    created = case_manager.create_case(case)
    return created


@app.get("/api/chargeback/evidence/{case_id}")
async def get_chargeback_evidence(case_id: str):
    case = case_manager.get_case(case_id)
    if not case:
        return {"error": "case not found"}
    evidence_result = evidence_engine.collect_evidence(case)
    # Flatten the prioritized evidence into the array the frontend expects
    priority_list = evidence_result.get("priority", [])
    evidence_items = []
    for item in priority_list:
        evidence_items.append({
            "category": item.get("category", ""),
            "type": item.get("label", ""),
            "description": item.get("label", ""),
            "value": item.get("data", {}),
            "strength": evidence_result.get("evidence_strength", 0),
            "collected_at": datetime.now(timezone.utc).isoformat(),
        })
    return {"case_id": case_id, "evidence": evidence_items}


@app.get("/api/chargeback/response/{case_id}")
async def get_chargeback_response(case_id: str):
    case = case_manager.get_case(case_id)
    if not case:
        return {"error": "case not found"}
    evidence_result = evidence_engine.collect_evidence(case)
    response = response_generator.generate_response(case, evidence_result)
    return {"case_id": case_id, "response": response}


@app.post("/api/chargeback/cases/{case_id}/status")
async def update_chargeback_status(case_id: str, body: dict):
    new_status = body.get("status", "")
    updated = case_manager.update_status(case_id, new_status)
    if not updated:
        return {"error": "case not found or invalid status"}
    return updated


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
            "recent_tx": recent_tx,
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
