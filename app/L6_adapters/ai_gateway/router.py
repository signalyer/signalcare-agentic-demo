"""Tier-based dispatch across concrete AI Gateway impls.

Fast → Ollama, Balanced/Reasoning → OpenRouter.

The router is itself an `AIGateway`, so callers upstream never see the concrete impls.
The whole cloud-agnostic property from ADR-0002 hinges on this file staying skinny — no
provider-specific logic, no format munging, no fallback ladders that leak per-provider
knowledge. Just dispatch.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from .base import (
    AIGateway,
    AIGatewayError,
    CompletionRequest,
    CompletionResponse,
    Tier,
)
from .local import OllamaGateway
from .openrouter import OpenRouterGateway


class TieredAIGateway(AIGateway):
    """Composite AI Gateway that routes by tier.

    Constructor injection allows tests to swap in mock gateways without touching env vars.
    Default construction wires the real Ollama + OpenRouter impls.
    """

    provider_name = "tiered-router"

    def __init__(
        self,
        local: AIGateway | None = None,
        hosted: AIGateway | None = None,
    ):
        self._local = local if local is not None else OllamaGateway()
        self._hosted = hosted if hosted is not None else OpenRouterGateway()

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

    async def close(self) -> None:
        # Close both — either may hold connection pools.
        await self._local.close()
        await self._hosted.close()
