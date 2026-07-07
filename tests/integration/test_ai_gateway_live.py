"""Live integration tests for the AI Gateway.

Auto-skips when providers are unavailable — see per-test skip guards. Under normal Week 1
development the developer runs these interactively; in CI they run when both providers
are reachable.

Per ADR-0004 the hosted tier uses the Anthropic SDK directly (not OpenRouter).
"""
from __future__ import annotations

import os

import httpx
import pytest

from L6_adapters.ai_gateway import (
    AnthropicGateway,
    CompletionRequest,
    Message,
    OllamaGateway,
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


def _anthropic_configured() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


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


@pytest.mark.skipif(not _anthropic_configured(), reason="ANTHROPIC_API_KEY not set")
async def test_anthropic_completion_returns_text():
    gateway = AnthropicGateway()
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
                trace_id="live-anthropic-1",
            )
        )
    finally:
        await gateway.close()

    assert result.text.strip(), "Anthropic returned empty text"
    assert result.provider == "anthropic"
    assert result.model
    assert result.latency_ms > 0
    assert result.trace_id == "live-anthropic-1"


@pytest.mark.skipif(
    not (_ollama_reachable() and _anthropic_configured()),
    reason="Requires BOTH Ollama and Anthropic — this is the ADR-0002 proof-point",
)
async def test_same_interface_serves_two_providers():
    """The load-bearing test for ADR-0002. Same CompletionRequest shape works for two
    genuinely different provider SDKs (Ollama REST + Anthropic SDK). Caller only touches Tier.
    """
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
    assert balanced.provider == "anthropic"
    # Two different provider SDKs, same interface shape:
    assert fast.text and balanced.text
    assert isinstance(fast.tokens_out, int) and isinstance(balanced.tokens_out, int)
