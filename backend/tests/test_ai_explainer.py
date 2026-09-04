import os

import pytest

os.environ.setdefault("AI_API_KEY", "")

from app.ai_explainer import explain_ring, _template_explanation, template_explanation


SAMPLE_RING = {
    "ring_id": "CAND-000",
    "score": 78.4,
    "members": ["F0000", "F0001", "F0002"],
    "signals": [
        {"name": "cycle_involvement", "weight": 0.3, "value": 0.9, "detail": "3/3 members on a cycle"},
        {"name": "community_isolation", "weight": 0.25, "value": 0.7, "detail": "dense internal ties"},
    ],
}


def test_template_explanation_is_deterministic_and_grounded():
    text1 = _template_explanation(SAMPLE_RING)
    text2 = _template_explanation(SAMPLE_RING)
    assert text1 == text2
    assert "CAND-000" in text1
    assert "cycle" in text1.lower() or "cycle_involvement".replace("_", " ") in text1


def test_template_explanation_public_wrapper():
    result = template_explanation(SAMPLE_RING)
    assert result["source"] == "template"
    assert "CAND-000" in result["text"]
    assert result["error"] is not None


@pytest.mark.asyncio
async def test_explain_ring_falls_back_without_api_key(monkeypatch):
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    result = await explain_ring(SAMPLE_RING)
    assert result["source"] == "template"
    assert result["error"] is not None
    assert "CAND-000" in result["text"]


@pytest.mark.asyncio
async def test_explain_ring_falls_back_on_network_error(monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "fake-key-for-test")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    class BoomClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **kw):
            raise RuntimeError("simulated network failure")

    monkeypatch.setattr("app.ai_explainer.httpx.AsyncClient", lambda **kw: BoomClient())
    result = await explain_ring(SAMPLE_RING)
    assert result["source"] == "template"
    assert "simulated network failure" in result["error"]
