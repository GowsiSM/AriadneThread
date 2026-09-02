"""
Controlled AI usage: "AI proposes and explains; deterministic code decides."

This module has exactly one job -- translate a structured, already-computed
ring detection result into a short plain-English explanation for a human
reviewer. It NEVER influences the risk score, the flag/no-flag decision, or
any money action. If the AI API is unreachable, unset, or errors out, the
system falls back to a deterministic templated explanation built directly
from the signal data -- the audit trail is never degraded, only the prose
quality is.

A second, offline function (`propose_heuristics`) is a design-time helper:
during development we asked an LLM to propose candidate detection heuristics
from a description of available graph features. We reviewed the output,
kept 4 of ~9 suggestions, and hard-coded those as deterministic functions in
detection.py. That transcript is included in docs/heuristic_proposals.md.
This function is NOT called at runtime by the detection pipeline.
"""
from __future__ import annotations

import os
import logging

import httpx

logger = logging.getLogger("fraud_sentinel.ai")

AI_API_KEY = os.getenv("AI_API_KEY", "").strip()
AI_API_BASE = os.getenv("AI_API_BASE", "https://api.openai.com/v1").rstrip("/")
AI_MODEL = os.getenv("AI_MODEL", "gpt-4o-mini")


def _template_explanation(ring: dict) -> str:
    top = sorted(ring["signals"], key=lambda s: s["weight"] * s["value"], reverse=True)
    lead = top[0]
    second = top[1] if len(top) > 1 else None
    size = len(ring["members"])
    parts = [
        f"Ring {ring['ring_id']} ({size} accounts, risk score {ring['score']}/100) "
        f"was flagged primarily on {lead['name'].replace('_', ' ')}: {lead['detail']}."
    ]
    if second:
        parts.append(f"Secondary signal -- {second['name'].replace('_', ' ')}: {second['detail']}.")
    parts.append("[templated explanation -- AI explainer unavailable, showing raw signal summary]")
    return " ".join(parts)


async def explain_ring(ring: dict) -> dict:
    """Returns {"text": str, "source": "ai"|"template", "error": str|None}."""
    if not AI_API_KEY:
        return {"text": _template_explanation(ring), "source": "template", "error": "AI_API_KEY not set"}

    prompt = (
        "You are explaining a fraud-ring detection result to a human fraud-ops "
        "reviewer. You are NOT deciding whether to act on it -- only explaining "
        "the already-computed signals in 2-3 plain English sentences, grounded "
        "strictly in the data given. Do not invent details.\n\n"
        f"Ring ID: {ring['ring_id']}\n"
        f"Member count: {len(ring['members'])}\n"
        f"Risk score (0-100, deterministic): {ring['score']}\n"
        "Signals:\n"
        + "\n".join(
            f"- {s['name']} (weight {s['weight']}, value {s['value']:.2f}): {s['detail']}"
            for s in ring["signals"]
        )
    )
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                f"{AI_API_BASE}/chat/completions",
                headers={"Authorization": f"Bearer {AI_API_KEY}"},
                json={
                    "model": AI_MODEL,
                    "temperature": 0.2,
                    "max_tokens": 180,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"].strip()
            return {"text": text, "source": "ai", "error": None}
    except Exception as exc:  # network error, timeout, bad response, quota, etc.
        logger.warning("AI explanation failed, falling back to template: %s", exc)
        return {"text": _template_explanation(ring), "source": "template", "error": str(exc)}
