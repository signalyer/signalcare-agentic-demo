"""Anthropic direct-SDK adapter — Balanced (Sonnet) + Reasoning (Opus) tiers.

Uses the official ``anthropic`` Python SDK. Chosen over a gateway proxy (OpenRouter) so
that the demo depends on Anthropic directly for hosted tiers — one fewer external
business dependency, and the adapter demonstrates a genuinely different provider SDK
sitting behind the same ``AIGateway`` interface (Ollama's REST vs Anthropic's SDK).

See ADR-0004 for the rationale over ADR-0002's original OpenRouter plan.

Anthropic API quirks handled here
---------------------------------
- ``system`` is a top-level parameter, NOT a message. We extract role="system" messages
  from ``CompletionRequest.messages`` and pass them separately.
- ``max_tokens`` is REQUIRED (unlike some providers where it's optional).
- Response text lives at ``resp.content[0].text``; usage counters are
  ``input_tokens`` / ``output_tokens`` (not ``prompt_tokens`` / ``completion_tokens``).
"""
from __future__ import annotations

import os
import time
from collections.abc import AsyncIterator

from anthropic import APIError, AsyncAnthropic

from .base import (
    AIGateway,
    AIGatewayError,
    CompletionRequest,
    CompletionResponse,
    Message,
    Tier,
)


class AnthropicGateway(AIGateway):
    """Concrete AI Gateway backed by Anthropic's official SDK."""

    provider_name = "anthropic"

    def __init__(
        self,
        api_key: str | None = None,
        reasoning_model: str | None = None,
        balanced_model: str | None = None,
    ):
        api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise AIGatewayError(
                "ANTHROPIC_API_KEY not set. Add it to .env before instantiating "
                "AnthropicGateway."
            )
        # Model IDs follow the CLAUDE.md declared defaults; override in .env to pin
        # a specific vintage.
        self.reasoning_model = reasoning_model or os.getenv(
            "ANTHROPIC_REASONING_MODEL", "claude-opus-4-7"
        )
        self.balanced_model = balanced_model or os.getenv(
            "ANTHROPIC_BALANCED_MODEL", "claude-sonnet-4-6"
        )
        self._client = AsyncAnthropic(api_key=api_key)

    def supports_tier(self, tier: Tier) -> bool:
        return tier in (Tier.BALANCED, Tier.REASONING)

    async def complete(self, req: CompletionRequest) -> CompletionResponse:
        model = self._model_for(req.tier)
        system, user_msgs = self._split_system(req.messages)
        kwargs = self._build_kwargs(model, req, system, user_msgs)
        started = time.perf_counter()
        try:
            resp = await self._client.messages.create(**kwargs)
        except APIError as exc:
            raise AIGatewayError(f"Anthropic request failed: {exc}") from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        text = ""
        if resp.content:
            # content is a list of content blocks; take the first text block.
            for block in resp.content:
                if getattr(block, "type", None) == "text":
                    text = getattr(block, "text", "") or ""
                    break

        usage = resp.usage
        return CompletionResponse(
            text=text,
            model=resp.model or model,
            provider=self.provider_name,
            tokens_in=getattr(usage, "input_tokens", 0),
            tokens_out=getattr(usage, "output_tokens", 0),
            latency_ms=latency_ms,
            trace_id=req.trace_id,
            raw=resp.model_dump() if hasattr(resp, "model_dump") else {},
        )

    async def stream(self, req: CompletionRequest) -> AsyncIterator[str]:
        model = self._model_for(req.tier)
        system, user_msgs = self._split_system(req.messages)
        kwargs = self._build_kwargs(model, req, system, user_msgs)
        try:
            async with self._client.messages.stream(**kwargs) as stream:
                async for piece in stream.text_stream:
                    if piece:
                        yield piece
        except APIError as exc:
            raise AIGatewayError(f"Anthropic stream failed: {exc}") from exc

    @staticmethod
    def _build_kwargs(
        model: str,
        req: CompletionRequest,
        system: str,
        user_msgs: list[Message],
    ) -> dict:
        """Build the kwargs dict for messages.create / messages.stream.

        Newer Claude models (Opus 4.7+, some others) reject ``temperature`` outright with
        400 ``temperature is deprecated for this model``. Older ones accept it. Rather
        than branch on model IDs (fragile — the deprecation set will grow), we omit
        ``temperature`` unless the caller explicitly set a non-default value.

        The internal default in ``CompletionRequest.temperature`` is 0.2. If we see that
        exact value, treat it as "no strong opinion" and let Anthropic apply its
        server-side default. Any other value = the caller cares, so pass it through
        (may 400 on Opus 4.7+; that surfaces via ``AIGatewayError``).
        """
        kwargs: dict = {
            "model": model,
            "max_tokens": req.max_tokens,
            "system": system or "You are a helpful assistant.",
            "messages": [{"role": m.role, "content": m.content} for m in user_msgs],
        }
        if req.temperature != 0.2:
            kwargs["temperature"] = req.temperature
        return kwargs

    def _model_for(self, tier: Tier) -> str:
        if tier is Tier.REASONING:
            return self.reasoning_model
        if tier is Tier.BALANCED:
            return self.balanced_model
        raise AIGatewayError(
            f"AnthropicGateway does not serve tier: {tier}. Fast is handled by OllamaGateway."
        )

    @staticmethod
    def _split_system(messages: list[Message]) -> tuple[str, list[Message]]:
        """Anthropic wants `system` at the top level. Extract it here."""
        system_parts: list[str] = []
        user_parts: list[Message] = []
        for m in messages:
            if m.role == "system":
                system_parts.append(m.content)
            else:
                user_parts.append(m)
        return "\n\n".join(system_parts), user_parts

    async def close(self) -> None:
        await self._client.close()
