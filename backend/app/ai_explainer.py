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


def template_explanation(ring: dict) -> dict:
    """Public wrapper that returns the standard explanation dict with a template.
    
    Used during streaming to avoid API calls; AI explanations are generated
    after the stream completes.
    """
    text = _template_explanation(ring)
    return {"text": text, "source": "template", "error": "AI explanations deferred until stream completes"}


def _build_prompt(ring: dict) -> str:
    return (
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


async def explain_ring(ring: dict) -> dict:
    """Returns {"text": str, "source": "ai"|"template", "error": str|None}."""
    cache_key = f"{ring.get('ring_id')}_{ring.get('score')}"
    if cache_key in _explanation_cache and _explanation_cache[cache_key].get("source") == "ai":
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
