"""Unit tests for the AI Gateway adapter.

Offline. No live provider calls. Constructor-inject fake adapters to verify router behavior
and interface contract.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from L6_adapters.ai_gateway import (
    AIGateway,
    AIGatewayError,
    CompletionRequest,
    CompletionResponse,
    Message,
    Tier,
    TieredAIGateway,
)


class _FakeGateway(AIGateway):
    """Records calls and returns canned responses. No network."""

    def __init__(self, name: str, supported: set[Tier]):
        self.name = name
        self._supported = supported
        self.calls: list[CompletionRequest] = []

    def supports_tier(self, tier: Tier) -> bool:
        return tier in self._supported

    async def complete(self, req: CompletionRequest) -> CompletionResponse:
        self.calls.append(req)
        return CompletionResponse(
            text=f"reply from {self.name}",
            model=f"{self.name}-model",
            provider=self.name,
            tokens_in=1,
            tokens_out=2,
            latency_ms=3,
            trace_id=req.trace_id,
        )

    async def stream(self, req: CompletionRequest) -> AsyncIterator[str]:
        self.calls.append(req)
        for piece in ("hel", "lo ", "world"):
            yield piece


def _req(tier: Tier, trace: str = "t1") -> CompletionRequest:
    return CompletionRequest(
        tier=tier,
        messages=[Message(role="user", content="hi")],
        trace_id=trace,
    )


class TestTierEnum:
    def test_string_values_are_stable(self):
        # These strings appear in .env, API contracts, telemetry — they must not drift.
        assert Tier.FAST.value == "fast"
        assert Tier.BALANCED.value == "balanced"
        assert Tier.REASONING.value == "reasoning"


class TestTieredRouter:
    def _router(self) -> tuple[TieredAIGateway, _FakeGateway, _FakeGateway]:
        local = _FakeGateway("local", {Tier.FAST})
        hosted = _FakeGateway("hosted", {Tier.BALANCED, Tier.REASONING})
        return TieredAIGateway(local=local, hosted=hosted), local, hosted

    async def test_fast_routes_to_local(self):
        router, local, hosted = self._router()
        resp = await router.complete(_req(Tier.FAST))
        assert resp.provider == "local"
        assert len(local.calls) == 1
        assert len(hosted.calls) == 0

    async def test_balanced_routes_to_hosted(self):
        router, local, hosted = self._router()
        resp = await router.complete(_req(Tier.BALANCED))
        assert resp.provider == "hosted"
        assert len(local.calls) == 0
        assert len(hosted.calls) == 1

    async def test_reasoning_routes_to_hosted(self):
        router, local, hosted = self._router()
        resp = await router.complete(_req(Tier.REASONING))
        assert resp.provider == "hosted"
        assert len(hosted.calls) == 1

    async def test_supports_tier_union(self):
        router, _, _ = self._router()
        assert router.supports_tier(Tier.FAST)
        assert router.supports_tier(Tier.BALANCED)
        assert router.supports_tier(Tier.REASONING)

    async def test_trace_id_propagates_through_router(self):
        router, local, _ = self._router()
        resp = await router.complete(_req(Tier.FAST, trace="tr-abc"))
        assert resp.trace_id == "tr-abc"
        assert local.calls[0].trace_id == "tr-abc"

    async def test_streaming_dispatches_to_correct_impl(self):
        router, local, hosted = self._router()
        chunks = [c async for c in router.stream(_req(Tier.FAST))]
        assert "".join(chunks) == "hello world"
        assert len(local.calls) == 1
        assert len(hosted.calls) == 0


class TestOllamaAdapterInternals:
    """Ollama-specific offline checks. No network."""

    def test_empty_messages_rejected(self):
        # Delayed import — .local doesn't need env vars to construct.
        from L6_adapters.ai_gateway.local import OllamaGateway

        gateway = OllamaGateway()
        with pytest.raises(AIGatewayError):
            gateway._build_payload(  # noqa: SLF001 — deliberate; unit-test internal invariant
                CompletionRequest(tier=Tier.FAST, messages=[]),
                stream=False,
            )

    def test_only_supports_fast(self):
        from L6_adapters.ai_gateway.local import OllamaGateway

        gateway = OllamaGateway()
        assert gateway.supports_tier(Tier.FAST)
        assert not gateway.supports_tier(Tier.BALANCED)
        assert not gateway.supports_tier(Tier.REASONING)


class TestAnthropicAdapterInternals:
    """Anthropic-specific offline checks. No network."""

    def test_missing_api_key_raises(self, monkeypatch):
        from L6_adapters.ai_gateway.anthropic_gateway import AnthropicGateway

        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(AIGatewayError):
            AnthropicGateway()

    def test_tier_to_model_mapping(self, monkeypatch):
        from L6_adapters.ai_gateway.anthropic_gateway import AnthropicGateway

        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake-but-nonempty")
        gateway = AnthropicGateway(
            reasoning_model="reasoning-x",
            balanced_model="balanced-x",
        )
        assert gateway._model_for(Tier.REASONING) == "reasoning-x"  # noqa: SLF001
        assert gateway._model_for(Tier.BALANCED) == "balanced-x"  # noqa: SLF001
        with pytest.raises(AIGatewayError):
            gateway._model_for(Tier.FAST)  # noqa: SLF001 — Anthropic doesn't serve Fast

    def test_system_split_pulls_out_system_messages(self, monkeypatch):
        from L6_adapters.ai_gateway.anthropic_gateway import AnthropicGateway

        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake-but-nonempty")
        system, user = AnthropicGateway._split_system(  # noqa: SLF001
            [
                Message(role="system", content="You are terse."),
                Message(role="user", content="Hi"),
                Message(role="assistant", content="Hello"),
                Message(role="system", content="Also polite."),
            ]
        )
        assert "You are terse." in system
        assert "Also polite." in system
        assert len(user) == 2
        assert [m.role for m in user] == ["user", "assistant"]

    def test_only_supports_balanced_and_reasoning(self, monkeypatch):
        from L6_adapters.ai_gateway.anthropic_gateway import AnthropicGateway

        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake-but-nonempty")
        gateway = AnthropicGateway()
        assert gateway.supports_tier(Tier.BALANCED)
        assert gateway.supports_tier(Tier.REASONING)
        assert not gateway.supports_tier(Tier.FAST)
