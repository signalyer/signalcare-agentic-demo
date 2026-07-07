"""BAA (Business Associate Agreement) gate — middleware that blocks LLM calls to
vendors not on the ``APPROVED_PHI_VENDORS`` allow-list.

This is the first L2 guardrail and the load-bearing enforcement point for
``CLAUDE.md`` non-negotiable rule 3: *"BAA gate is real middleware. Every LLM call
passes through ``app/L2_guardrails/baa_gate.py``. No exceptions."*

The gate is a decorator over ``TieredAIGateway`` — see ADR-0005 for the
wrap-the-router-not-the-adapters rationale. ``BAAGateGuard`` itself implements
``AIGateway``, so upstream callers (``main.py``, future L3 agents, orchestrator)
still interact with a single ``AIGateway`` type. The guard is invisible until it
fires.

Denial surface
--------------
A rejected call raises :class:`BAAGateError`. That exception is intentionally NOT
a subclass of :class:`AIGatewayError` — a BAA denial is a *policy decision* callers
must never bypass, whereas an ``AIGatewayError`` is a transient issue callers may
retry. Different failure classes deserve different exception types and different
HTTP codes (451 vs 502). ``main.py`` registers a FastAPI exception handler that
maps :class:`BAAGateError` to HTTP 451 (Unavailable For Legal Reasons, RFC 7725).

Configuration
-------------
Read from env at guard construction (not per-call):

- ``REQUIRE_BAA`` — ``true``/``false``. When ``false``, the guard forwards every call
  without checking. Default in ``.env.example`` is ``true``.
- ``APPROVED_PHI_VENDORS`` — comma-separated vendor names (case-insensitive) that
  MAY receive PHI. Compared against the target adapter's ``provider_name`` (also
  case-insensitive). Default in ``.env.example`` is ``anthropic,ollama``.
"""
from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator

from L6_adapters.ai_gateway import (
    AIGateway,
    CompletionRequest,
    CompletionResponse,
    Tier,
    TieredAIGateway,
)

_logger = logging.getLogger("signalcare.baa_gate")


class BAAGateError(Exception):
    """Raised when a request targets a vendor not on ``APPROVED_PHI_VENDORS``.

    Carries the offending ``vendor`` name and the request's ``trace_id`` so the
    HTTP 451 handler and the audit log both have queryable context.
    """

    def __init__(self, vendor: str, trace_id: str | None = None):
        self.vendor = vendor
        self.trace_id = trace_id
        super().__init__(
            f"BAA required: vendor '{vendor}' is not in APPROVED_PHI_VENDORS"
        )


class BAAGateGuard(AIGateway):
    """AIGateway decorator that enforces BAA policy before delegating.

    Wraps a ``TieredAIGateway`` (or anything shaped like one — must expose
    ``vendor_for(tier)`` and the standard ``AIGateway`` methods). The guard
    itself is an ``AIGateway``, so callers upstream see no interface change.
    """

    provider_name = "baa-gate"

    def __init__(
        self,
        inner: TieredAIGateway,
        *,
        require_baa: bool | None = None,
        approved_vendors: frozenset[str] | None = None,
    ):
        self._inner = inner
        self._require_baa, self._approved = self._resolve_config(
            require_baa, approved_vendors
        )
        _logger.info(
            "baa_gate_initialized require_baa=%s approved_vendors=%s",
            self._require_baa,
            sorted(self._approved) or "<empty>",
        )

    @staticmethod
    def _resolve_config(
        require_baa: bool | None,
        approved_vendors: frozenset[str] | None,
    ) -> tuple[bool, frozenset[str]]:
        if require_baa is None:
            raw = os.getenv("REQUIRE_BAA", "true").strip().lower()
            require_baa = raw in ("1", "true", "yes", "on")
        if approved_vendors is None:
            raw = os.getenv("APPROVED_PHI_VENDORS", "")
            approved_vendors = frozenset(
                v.strip().lower() for v in raw.split(",") if v.strip()
            )
        return require_baa, approved_vendors

    def supports_tier(self, tier: Tier) -> bool:
        return self._inner.supports_tier(tier)

    async def complete(self, req: CompletionRequest) -> CompletionResponse:
        self._enforce(req)
        return await self._inner.complete(req)

    async def stream(self, req: CompletionRequest) -> AsyncIterator[str]:
        # Enforce BEFORE opening the upstream stream so no bytes leave the process
        # on a denied call.
        self._enforce(req)
        async for chunk in self._inner.stream(req):
            yield chunk

    async def close(self) -> None:
        await self._inner.close()

    def _enforce(self, req: CompletionRequest) -> None:
        if not self._require_baa:
            return
        vendor = self._inner.vendor_for(req.tier).lower()
        if vendor in self._approved:
            _logger.info(
                "baa_gate_decision decision=allow vendor=%s tier=%s trace_id=%s",
                vendor,
                req.tier.value,
                req.trace_id,
            )
            return
        _logger.warning(
            "baa_gate_decision decision=deny vendor=%s tier=%s trace_id=%s",
            vendor,
            req.tier.value,
            req.trace_id,
        )
        raise BAAGateError(vendor, req.trace_id)
