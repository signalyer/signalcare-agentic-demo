"""OpenRouter adapter — Balanced + Reasoning tiers, hosted.

OpenRouter exposes an OpenAI-compatible API surface, so we reuse the `openai` client with a
custom `base_url`. This keeps the adapter minimal and inherits streaming + typed responses
from the OpenAI SDK.

Model IDs come from env so tier→model mapping stays configuration, not code.
"""
from __future__ import annotations

import os
import time
from collections.abc import AsyncIterator

from openai import APIError, AsyncOpenAI

from .base import (
    AIGateway,
    AIGatewayError,
    CompletionRequest,
    CompletionResponse,
    Tier,
)

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterGateway(AIGateway):
    """Concrete AI Gateway backed by OpenRouter (routes to Claude / GPT / etc)."""

    provider_name = "openrouter"

    def __init__(
        self,
        api_key: str | None = None,
        reasoning_model: str | None = None,
        balanced_model: str | None = None,
        fast_model: str | None = None,
    ):
        api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not api_key or api_key.startswith("sk-or-v1-REPLACE"):
            raise AIGatewayError(
                "OPENROUTER_API_KEY not set (or still the .env.example placeholder). "
                "Set a real key in .env before instantiating OpenRouterGateway."
            )
        self.reasoning_model = reasoning_model or os.getenv(
            "OPENROUTER_REASONING_MODEL", "anthropic/claude-opus-4-7"
        )
        self.balanced_model = balanced_model or os.getenv(
            "OPENROUTER_BALANCED_MODEL", "anthropic/claude-sonnet-4-6"
        )
        # Hosted Fast is used only if the local Ollama impl is unavailable.
        self.fast_model = fast_model or os.getenv(
            "OPENROUTER_FAST_MODEL", "anthropic/claude-haiku-4-5"
        )
        self._client = AsyncOpenAI(base_url=_OPENROUTER_BASE_URL, api_key=api_key)

    def supports_tier(self, tier: Tier) -> bool:
        # Hosted covers Balanced and Reasoning natively; supports Fast as a fallback
        # only if the router chooses to route there (see router.py).
        return tier in (Tier.BALANCED, Tier.REASONING, Tier.FAST)

    async def complete(self, req: CompletionRequest) -> CompletionResponse:
        model = self._model_for(req.tier)
        started = time.perf_counter()
        try:
            resp = await self._client.chat.completions.create(
                model=model,
                messages=[{"role": m.role, "content": m.content} for m in req.messages],
                max_tokens=req.max_tokens,
                temperature=req.temperature,
            )
        except APIError as exc:
            raise AIGatewayError(f"OpenRouter request failed: {exc}") from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        text = (resp.choices[0].message.content or "") if resp.choices else ""
        usage = resp.usage
        return CompletionResponse(
            text=text,
            model=model,
            provider=self.provider_name,
            tokens_in=usage.prompt_tokens if usage else 0,
            tokens_out=usage.completion_tokens if usage else 0,
            latency_ms=latency_ms,
            trace_id=req.trace_id,
            raw=resp.model_dump() if hasattr(resp, "model_dump") else {},
        )

    async def stream(self, req: CompletionRequest) -> AsyncIterator[str]:
        model = self._model_for(req.tier)
        try:
            stream = await self._client.chat.completions.create(
                model=model,
                messages=[{"role": m.role, "content": m.content} for m in req.messages],
                max_tokens=req.max_tokens,
                temperature=req.temperature,
                stream=True,
            )
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                piece = getattr(delta, "content", None)
                if piece:
                    yield piece
        except APIError as exc:
            raise AIGatewayError(f"OpenRouter stream failed: {exc}") from exc

    def _model_for(self, tier: Tier) -> str:
        if tier is Tier.REASONING:
            return self.reasoning_model
        if tier is Tier.BALANCED:
            return self.balanced_model
        if tier is Tier.FAST:
            return self.fast_model
        raise AIGatewayError(f"Unsupported tier for OpenRouter: {tier}")

    async def close(self) -> None:
        await self._client.close()
