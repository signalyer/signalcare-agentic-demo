"""Ollama adapter — Fast tier, runs on localhost.

For Week 1 (see ADR-0003) Ollama runs as a native Windows service on
`http://localhost:11434`, not in a container. From Phase 3 onward it can move back into
the docker-compose stack without changing this file.

Native install:
    winget install Ollama.Ollama
    ollama pull llama3.2:3b
"""
from __future__ import annotations

import os
import time
from collections.abc import AsyncIterator

import httpx

from .base import (
    AIGateway,
    AIGatewayError,
    CompletionRequest,
    CompletionResponse,
    Message,
    Tier,
)

# Fallback to localhost (native install), not the docker-compose service name.
# .env.example sets OLLAMA_HOST=http://ollama:11434 for the compose stack; override in .env
# during Weeks 1-2 per ADR-0003.
_DEFAULT_HOST = "http://localhost:11434"
_DEFAULT_MODEL = "llama3.2:3b"


class OllamaGateway(AIGateway):
    """Concrete AI Gateway backed by Ollama's `/api/chat`."""

    provider_name = "ollama"

    def __init__(
        self,
        host: str | None = None,
        fast_model: str | None = None,
        timeout_seconds: float = 120.0,
    ):
        self.host = host or os.getenv("OLLAMA_HOST", _DEFAULT_HOST)
        self.fast_model = fast_model or os.getenv("OLLAMA_FAST_MODEL", _DEFAULT_MODEL)
        self._client = httpx.AsyncClient(base_url=self.host, timeout=timeout_seconds)

    def supports_tier(self, tier: Tier) -> bool:
        return tier is Tier.FAST

    async def complete(self, req: CompletionRequest) -> CompletionResponse:
        payload = self._build_payload(req, stream=False)
        started = time.perf_counter()
        try:
            resp = await self._client.post("/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            raise AIGatewayError(f"Ollama request failed: {exc}") from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        return CompletionResponse(
            text=(data.get("message") or {}).get("content", ""),
            model=data.get("model", self.fast_model),
            provider=self.provider_name,
            tokens_in=data.get("prompt_eval_count", 0),
            tokens_out=data.get("eval_count", 0),
            latency_ms=latency_ms,
            trace_id=req.trace_id,
            raw=data,
        )

    async def stream(self, req: CompletionRequest) -> AsyncIterator[str]:
        payload = self._build_payload(req, stream=True)
        try:
            async with self._client.stream("POST", "/api/chat", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    # Ollama streams NDJSON: one JSON object per line.
                    import json

                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    piece = (chunk.get("message") or {}).get("content", "")
                    if piece:
                        yield piece
                    if chunk.get("done"):
                        break
        except httpx.HTTPError as exc:
            raise AIGatewayError(f"Ollama stream failed: {exc}") from exc

    def _build_payload(self, req: CompletionRequest, *, stream: bool) -> dict:
        if not req.messages:
            raise AIGatewayError("CompletionRequest.messages must be non-empty")
        return {
            "model": self.fast_model,
            "messages": [self._msg(m) for m in req.messages],
            "stream": stream,
            "options": {
                "num_predict": req.max_tokens,
                "temperature": req.temperature,
            },
        }

    @staticmethod
    def _msg(m: Message) -> dict:
        return {"role": m.role, "content": m.content}

    async def close(self) -> None:
        await self._client.aclose()
