"""Live integration tests for the AI Gateway.

Auto-skips when providers are unavailable — see per-test skip guards. Under normal Week 1
development the developer runs these interactively; in CI they run when both providers
are reachable.
"""
from __future__ import annotations

import os

import httpx
import pytest

from L6_adapters.ai_gateway import (
    CompletionRequest,
    Message,
    OllamaGateway,
    OpenRouterGateway,
    Tier,
)

pytestmark = pytest.mark.integration


def _ollama_reachable() -> bool:
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    try:
        with httpx.Client(timeout=2.0) as client:
            r = client.get(f"{host}/api/tags")
            return r.status_code == 200
    except httpx.HTTPError:
        return False


def _openrouter_configured() -> bool:
    key = os.getenv("OPENROUTER_API_KEY", "")
    return bool(key) and not key.startswith("sk-or-v1-REPLACE")


@pytest.mark.skipif(not _ollama_reachable(), reason="Ollama not reachable on OLLAMA_HOST")
async def test_ollama_completion_returns_text():
    gateway = OllamaGateway()
    try:
        result = await gateway.complete(
            CompletionRequest(
                tier=Tier.FAST,
                messages=[
                    Message(role="system", content="Reply in exactly one word."),
                    Message(role="user", content="What color is the sky on a clear day?"),
                ],
                max_tokens=16,
                temperature=0.0,
                trace_id="live-ollama-1",
            )
        )
    finally:
        await gateway.close()

    assert result.text.strip(), "Ollama returned empty text"
    assert result.provider == "ollama"
    assert result.model  # non-empty
    assert result.latency_ms > 0
    assert result.trace_id == "live-ollama-1"


@pytest.mark.skipif(not _openrouter_configured(), reason="OPENROUTER_API_KEY not set")
async def test_openrouter_completion_returns_text():
    gateway = OpenRouterGateway()
    try:
        result = await gateway.complete(
            CompletionRequest(
                tier=Tier.BALANCED,
                messages=[
                    Message(role="system", content="Reply in exactly one word."),
                    Message(role="user", content="What color is grass?"),
                ],
                max_tokens=16,
                temperature=0.0,
                trace_id="live-openrouter-1",
            )
        )
    finally:
        await gateway.close()

    assert result.text.strip(), "OpenRouter returned empty text"
    assert result.provider == "openrouter"
    assert result.model
    assert result.latency_ms > 0
    assert result.trace_id == "live-openrouter-1"


@pytest.mark.skipif(
    not (_ollama_reachable() and _openrouter_configured()),
    reason="Requires BOTH Ollama and OpenRouter — this is the ADR-0002 proof-point",
)
async def test_same_interface_serves_two_providers():
    """The load-bearing test for ADR-0002. Same CompletionRequest shape works for both
    providers; caller only touches Tier."""
    from L6_adapters.ai_gateway import TieredAIGateway

    router = TieredAIGateway()
    try:
        fast = await router.complete(
            CompletionRequest(
                tier=Tier.FAST,
                messages=[Message(role="user", content="Say hi.")],
                max_tokens=16,
                trace_id="live-both-fast",
            )
        )
        balanced = await router.complete(
            CompletionRequest(
                tier=Tier.BALANCED,
                messages=[Message(role="user", content="Say hi.")],
                max_tokens=16,
                trace_id="live-both-balanced",
            )
        )
    finally:
        await router.close()

    assert fast.provider == "ollama"
    assert balanced.provider == "openrouter"
    # Two different providers, same interface shape:
    assert fast.text and balanced.text
    assert isinstance(fast.tokens_out, int) and isinstance(balanced.tokens_out, int)
