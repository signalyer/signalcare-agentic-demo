"""AI Gateway abstract interface.

Concrete implementations live in `local.py` (Ollama) and `openrouter.py` (hosted).
The `router.py` composite dispatches between them by `Tier`.

Design notes
------------
- **Providers are hidden from callers.** A caller says "Fast tier" and gets back text plus
  metadata — never a provider-specific object. This is the load-bearing property from ADR-0002.
- **Errors are wrapped.** Concrete impls MUST catch provider-specific exceptions and raise
  `AIGatewayError` so callers can handle a single error type. If a provider quirk leaks past
  this boundary, the abstraction is broken.
- **Immutable request/response.** Frozen dataclasses. Any structured mutation belongs in a
  new instance, not a mutated field.
- **`trace_id` is propagated but not synthesized here.** The L1/L4 layer generates it and
  passes it in; the adapter just carries it into logs and back into the response.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import Enum


class Tier(str, Enum):
    """Model tier. Selection is caller-driven; router does the mapping to provider."""

    FAST = "fast"          # local latency-sensitive: Ollama by default
    BALANCED = "balanced"  # hosted mid-tier: Claude Sonnet via OpenRouter
    REASONING = "reasoning"  # hosted top-tier: Claude Opus via OpenRouter


@dataclass(frozen=True)
class Message:
    """One chat turn. Role must be system|user|assistant."""

    role: str
    content: str


@dataclass(frozen=True)
class CompletionRequest:
    """Everything an adapter needs to produce a completion.

    Callers set `tier` — providers are chosen by `router.py`, never by the caller.

    ``phi_present`` / ``phi_tier`` are set by the L2 PHI redactor guardrail (see
    ``app/L2_guardrails/phi_redactor.py``) via ``dataclasses.replace``. Downstream
    guardrails — specifically the BAA gate — consult ``phi_present`` to decide
    allow/deny. Callers upstream of the redactor leave both fields at defaults;
    callers that bypass the redactor stay at defaults, which is semantically
    "no PHI claimed" — a defense-in-depth default that never accidentally
    weakens enforcement. See ADR-0006.
    """

    tier: Tier
    messages: list[Message]
    max_tokens: int = 1024
    temperature: float = 0.2
    trace_id: str | None = None
    phi_present: bool = False
    phi_tier: str | None = None  # "T1" | "T2" | "T3" | "T4" | None


@dataclass(frozen=True)
class CompletionResponse:
    """Provider-agnostic response envelope.

    `provider` and `model` are surfaced so telemetry can distinguish which impl served
    the call — but callers should not branch on them.
    """

    text: str
    model: str
    provider: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    trace_id: str | None = None
    raw: dict = field(default_factory=dict)  # unstructured provider metadata for debugging


class AIGatewayError(Exception):
    """Provider-agnostic error from any AI Gateway impl.

    Concrete impls wrap httpx.HTTPError, openai.APIError, connection refused, etc.
    Callers only ever catch this type.
    """


class AIGateway(ABC):
    """Abstract AI Gateway. Two operations: complete (blocking) and stream (chunked).

    Tool-calling (`with_tools`) will be added in Phase 2 when the first tool-calling agent
    (compliance/ops digest) needs it. Not scaffolded here to avoid speculative abstraction —
    see project CLAUDE.md persona.
    """

    @abstractmethod
    async def complete(self, req: CompletionRequest) -> CompletionResponse:
        """Return a full completion. Wrap provider errors as AIGatewayError."""

    @abstractmethod
    def stream(self, req: CompletionRequest) -> AsyncIterator[str]:
        """Yield text chunks as they arrive. Wrap provider errors as AIGatewayError.

        Signature is a plain method returning an async iterator (not `async def`) so that
        callers can `async for chunk in gateway.stream(req)` without an extra await.
        Concrete impls should be implemented as async generators.
        """

    @abstractmethod
    def supports_tier(self, tier: Tier) -> bool:
        """True iff this adapter is willing to service `tier`."""

    async def close(self) -> None:
        """Release resources (HTTP clients, etc.). Default: no-op."""
        return None
