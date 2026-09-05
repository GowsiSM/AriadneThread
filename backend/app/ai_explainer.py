"""
Controlled AI usage: "AI proposes and explains; deterministic code decides."

This module has exactly one job -- translate a structured, already-computed
ring detection result into a short plain-English explanation for a human
reviewer. It NEVER influences the risk score, the flag/no-flag decision, or
any money action. If the AI API is unreachable, unset, or errors out, the
system falls back to a deterministic templated explanation built directly
from the signal data -- the audit trail is never degraded, only the prose
quality is.

Provider selection (in order of preference):
  1. Google Gemini  -- when GEMINI_API_KEY is set (uses the google-genai SDK).
  2. OpenAI-compatible -- when AI_API_KEY is set (uses httpx).
  3. Deterministic template -- always available as the final fallback.

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

# OpenAI-compatible endpoint (optional). Used ONLY to generate plain-English
# explanations of already-detected rings. Never used for detection or decisions.
AI_API_BASE = os.getenv("AI_API_BASE", "https://api.openai.com/v1").rstrip("/")
AI_MODEL = os.getenv("AI_MODEL", "gpt-4o-mini")

# Explanation cache by (ring_id, score) to avoid redundant API calls and rate limits
_explanation_cache: dict[str, dict] = {}


def _get_gemini_config() -> tuple[str, str]:
    """Dynamically read key and model from environment."""
    key = os.getenv("GEMINI_API_KEY", "").strip()
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
    # Auto-migrate deprecated or sunset model names
    if model in ("gemini-2.0-flash", "gemini-1.5-flash"):
        model = "gemini-2.5-flash"
    return key, model


def _synthesize_fraud_explanation(ring: dict) -> str:
    """Generate an authoritative, articulate fraud intelligence explanation
    synthesizing graph signals, typologies, flow dynamics, roles, and motifs.
    """
    signals = ring.get("signals", [])
    top = sorted(signals, key=lambda s: s.get("weight", 0) * s.get("value", 0), reverse=True)
    lead = top[0] if top else {"name": "risk signals", "detail": "elevated anomaly score"}
    second = top[1] if len(top) > 1 else None
    size = len(ring.get("members", []))
    score = ring.get("score", 0.0)
    typology = ring.get("typology")
    flow = ring.get("flow_summary")
    motifs = ring.get("motifs", [])
    roles = ring.get("roles", [])

    typology_str = f" exhibiting a {typology.replace('_', ' ')} typology pattern" if typology else ""
    parts = [
        f"Ring {ring.get('ring_id', 'CAND')} comprises {size} coordinated accounts flagged with a risk score of {score}/100{typology_str}."
    ]

    lead_name = lead["name"].replace("_", " ")
    parts.append(f"Primary risk driver is {lead_name}: {lead.get('detail', '')}.")
    if second:
        sec_name = second["name"].replace("_", " ")
        parts.append(f"Secondary compounding indicator is {sec_name}: {second.get('detail', '')}.")

    if flow and isinstance(flow, dict):
        int_vol = flow.get("internal_volume", 0)
        ratio = flow.get("flow_ratio", 0)
        dom_path = flow.get("dominant_path", [])
        if int_vol > 0 or ratio > 0:
            flow_desc = f"Internal money flow reached ₹{int_vol:,.2f} with a flow ratio of {ratio:.2f}"
            if dom_path and len(dom_path) >= 2:
                flow_desc += f", with velocity concentrated on {' → '.join(dom_path)}"
            flow_desc += "."
            parts.append(flow_desc)

    if motifs:
        motif_names = sorted({
            ((m.get("motif_type") if isinstance(m, dict) else getattr(m, "motif_type", None)) or "").replace("_", " ")
            for m in motifs
            if (m.get("motif_type") if isinstance(m, dict) else getattr(m, "motif_type", None))
        })
        if motif_names:
            parts.append(f"Detected graph motifs include: {', '.join(motif_names)}.")

    if roles:
        role_map = {}
        for r in roles:
            role_name = r.get("role") if isinstance(r, dict) else getattr(r, "role", "")
            user_id = r.get("user_id") if isinstance(r, dict) else getattr(r, "user_id", "")
            if role_name and user_id:
                role_map.setdefault(role_name, []).append(user_id)
        role_highlights = []
        for role_name, members in role_map.items():
            if role_name in ("intermediary", "aggregator", "source", "mule"):
                role_highlights.append(f"{role_name.replace('_', ' ')} ({', '.join(members[:3])})")
        if role_highlights:
            parts.append(f"Key identified account roles: {'; '.join(role_highlights)}.")

    return " ".join(parts)


def _template_explanation(ring: dict) -> str:
    return _synthesize_fraud_explanation(ring)


def template_explanation(ring: dict) -> dict:
    """Public wrapper that returns the standard explanation dict with a synthesized explanation."""
    text = _synthesize_fraud_explanation(ring)
    return {"text": text, "source": "template", "error": "AI explanations deferred until stream completes"}


def _build_prompt(ring: dict) -> str:
    prompt_lines = [
        "You are explaining a fraud-ring detection result to a human fraud-ops "
        "reviewer. You are NOT deciding whether to act on it -- only explaining "
        "the already-computed signals in 2-3 plain English sentences, grounded "
        "strictly in the data given. Do not invent details.\n",
        f"Ring ID: {ring['ring_id']}",
        f"Member count: {len(ring['members'])}",
        f"Risk score (0-100, deterministic): {ring['score']}",
    ]
    if ring.get("typology"):
        prompt_lines.append(f"Detected Typology: {ring['typology']}")
    prompt_lines.append("Signals:")
    for s in ring.get("signals", []):
        prompt_lines.append(f"- {s['name']} (weight {s['weight']}, value {s['value']:.2f}): {s['detail']}")
    if ring.get("flow_summary") and isinstance(ring["flow_summary"], dict):
        f_s = ring["flow_summary"]
        prompt_lines.append(f"Money Flow: internal={f_s.get('internal_volume', 0):.2f}, ratio={f_s.get('flow_ratio', 0):.2f}, path={f_s.get('dominant_path', [])}")
    return "\n".join(prompt_lines)


async def _gemini_explanation(ring: dict) -> dict:
    """Call the Gemini API via REST (httpx) or google-genai SDK. Returns result dict."""
    gemini_key, gemini_model = _get_gemini_config()
    if not gemini_key:
        return {"text": _template_explanation(ring), "source": "template", "error": "no Gemini API key set"}

    model_clean = gemini_model.replace("models/", "")
    prompt = _build_prompt(ring)

    # 1. Primary: Direct REST call using httpx (resilient, no SDK dependency)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_clean}:generateContent?key={gemini_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 220,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts and "text" in parts[0]:
                        text = parts[0]["text"].strip()
                        if text:
                            return {"text": text, "source": "ai", "error": None}
                raise ValueError("Gemini API returned an empty or unparseable response")
            else:
                err_detail = resp.text[:300]
                logger.warning("Gemini REST API error %d: %s", resp.status_code, err_detail)
                raise RuntimeError(f"Gemini API error {resp.status_code}: {err_detail}")
    except Exception as exc:
        # 2. Secondary fallback: try SDK if installed
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=gemini_key)
            response = client.models.generate_content(
                model=model_clean,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=220),
            )
            text = (response.text or "").strip()
            if text:
                return {"text": text, "source": "ai", "error": None}
        except Exception:
            pass

        logger.warning("Gemini explanation failed, falling back to template: %s", exc)
        return {"text": _template_explanation(ring), "source": "template", "error": str(exc)}


async def _openai_explanation(ring: dict) -> dict:
    """Call an OpenAI-compatible endpoint via httpx. Returns the result dict."""
    ai_api_key = os.getenv("AI_API_KEY", "").strip()
    if not ai_api_key:
        return {"text": _template_explanation(ring), "source": "template", "error": "AI_API_KEY not set"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{AI_API_BASE}/chat/completions",
                headers={"Authorization": f"Bearer {ai_api_key}"},
                json={
                    "model": AI_MODEL,
                    "temperature": 0.2,
                    "max_tokens": 200,
                    "messages": [{"role": "user", "content": _build_prompt(ring)}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"].strip()
            return {"text": text, "source": "ai", "error": None}
    except Exception as exc:
        logger.warning("AI explanation failed, falling back to template: %s", exc)
        return {"text": _template_explanation(ring), "source": "template", "error": str(exc)}


async def explain_ring(ring: dict, force_refresh: bool = False) -> dict:
    """Returns {"text": str, "source": "ai"|"template", "error": str|None}."""
    cache_key = f"{ring.get('ring_id')}_{ring.get('score')}"
    if not force_refresh and cache_key in _explanation_cache and _explanation_cache[cache_key].get("source") == "ai":
        return _explanation_cache[cache_key]

    gemini_key, _ = _get_gemini_config()
    openai_key = os.getenv("AI_API_KEY", "").strip()

    result = None
    if gemini_key:
        result = await _gemini_explanation(ring)
        if result["source"] == "ai":
            _explanation_cache[cache_key] = result
            return result
        # If Gemini returned error and OpenAI is also available, try OpenAI
        if openai_key:
            res_openai = await _openai_explanation(ring)
            if res_openai["source"] == "ai":
                _explanation_cache[cache_key] = res_openai
                return res_openai
        return result

    if openai_key:
        result = await _openai_explanation(ring)
        if result["source"] == "ai":
            _explanation_cache[cache_key] = result
        return result

    return {"text": _template_explanation(ring), "source": "template", "error": "no AI API key set"}
