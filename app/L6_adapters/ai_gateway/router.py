"""Tier-based dispatch across concrete AI Gateway impls.

Fast → Ollama (local), Balanced/Reasoning → Anthropic (hosted, direct SDK).

Per ADR-0004 the hosted tier uses the Anthropic SDK directly rather than routing
through OpenRouter — one fewer external dependency, and the demo showcases two
genuinely different provider SDKs (Ollama REST + Anthropic SDK) behind the same
``AIGateway`` interface.

The router is itself an ``AIGateway``, so callers upstream never see the concrete
impls. The whole cloud-agnostic property from ADR-0002 hinges on this file staying
skinny — no provider-specific logic, no format munging. Just dispatch.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from .anthropic_gateway import AnthropicGateway
from .base import (
    AIGateway,
    AIGatewayError,
    CompletionRequest,
    CompletionResponse,
    Tier,
)
from .local import OllamaGateway


class TieredAIGateway(AIGateway):
    """Composite AI Gateway that routes by tier.

    Constructor injection allows tests to swap in mock gateways without touching env vars.
    Default construction wires the real Ollama + Anthropic impls.
    """

    provider_name = "tiered-router"

    def __init__(
        self,
        local: AIGateway | None = None,
        hosted: AIGateway | None = None,
    ):
        self._local = local if local is not None else OllamaGateway()
        self._hosted = hosted if hosted is not None else AnthropicGateway()

    def supports_tier(self, tier: Tier) -> bool:
        return self._local.supports_tier(tier) or self._hosted.supports_tier(tier)

    async def complete(self, req: CompletionRequest) -> CompletionResponse:
        return await self._pick(req.tier).complete(req)

    async def stream(self, req: CompletionRequest) -> AsyncIterator[str]:
        async for chunk in self._pick(req.tier).stream(req):
            yield chunk

    def _pick(self, tier: Tier) -> AIGateway:
        if tier is Tier.FAST:
            return self._local
        if tier in (Tier.BALANCED, Tier.REASONING):
            return self._hosted
        raise AIGatewayError(f"No adapter for tier: {tier}")

    def vendor_for(self, tier: Tier) -> str:
        """Return the ``provider_name`` of the concrete adapter that would serve ``tier``.

        Used by ``L2_guardrails.baa_gate.BAAGateGuard`` to make the vendor identity
        available *before* the call is dispatched — so the guard can allow/deny based
        on ``APPROVED_PHI_VENDORS`` without needing to know the tier-to-adapter mapping
        itself. See ADR-0005.
        """
        return getattr(self._pick(tier), "provider_name", "unknown")

    async def close(self) -> None:
        # Close both — either may hold connection pools.
        await self._local.close()
        await self._hosted.close()
