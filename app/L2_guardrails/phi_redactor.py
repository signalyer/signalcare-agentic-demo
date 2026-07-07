"""PHI (Protected Health Information) redactor — L2 guardrail that scans outbound
LLM message content, redacts detected PHI at configured tiers, and tags the
request with ``phi_present`` + ``phi_tier`` so the BAA gate downstream can
enforce policy.

Middleware shape and ordering
-----------------------------
Same shape as :class:`L2_guardrails.baa_gate.BAAGateGuard` — a decorator that
implements :class:`AIGateway` by delegating to a wrapped inner gateway. See
ADR-0006 for why the redactor is the outermost guardrail in the L2 stack
(runs first, sets the flag the BAA gate consults) and ADR-0005 for the
underlying wrap-the-router pattern.

Runtime composition in ``main.py``::

    router = TieredAIGateway()          # L6
    gated  = BAAGateGuard(router)       # L2 — reads phi_present
    stack  = PHIRedactor(gated)         # L2 — sets phi_present. Outermost.

Detection approach
------------------
Pragmatic regex-first. Enough to demonstrate the T1-T4 tiering, small enough
to reason about. The swap-in point for a production-grade detector (Presidio
+ named-entity recognition) is :func:`_scan_content` — replace the regex loop
with the Presidio Analyzer and preserve the return shape.

Tier taxonomy
-------------
- **T1** (highest sensitivity): SSN, MRN, credit-card number
- **T2** (high): email, phone number, formatted date-of-birth (MM/DD/YYYY),
  street address with common suffix
- **T3** (low): standalone ZIP code, standalone age
- **T4**: no PHI detected

``phi_tier`` on the outgoing request is the *max* tier detected across all
messages — a call with one T2 email and one T3 ZIP is tagged ``T2``.

Redaction modes
---------------
Via env ``REDACTION_MODE`` (loaded once at guard construction):

- ``strict`` (default): redact T1 and T2 matches to ``[REDACTED-<KIND>]``
  tokens.
- ``standard``: redact T1 only. T2 is tagged but content passed through.
- ``off``: detect and tag ``phi_present`` / ``phi_tier``, but do not mutate
  content. Useful for observability-only rollouts.

In all three modes the request is tagged. Only the content differs.

Non-goals
---------
- No LLM-based PHI classification (Phase 4 concern per build-plan line 65).
- No reversible token map for re-hydration (out of scope for demo).
- No memoization across sessions (each request scanned fresh).
"""
from __future__ import annotations

import dataclasses
import logging
import os
import re
from collections.abc import AsyncIterator
from typing import NamedTuple

from L6_adapters.ai_gateway import (
    AIGateway,
    CompletionRequest,
    CompletionResponse,
    Message,
    Tier,
)

_logger = logging.getLogger("signalcare.phi_redactor")


class _Pattern(NamedTuple):
    """One detector: name, tier, compiled regex, redaction label."""

    name: str
    tier: str  # "T1" | "T2" | "T3"
    regex: re.Pattern[str]
    label: str


# Order matters: more-specific patterns first, so `\d{5}` ZIP does not steal
# a match from `\d{3}-\d{2}-\d{4}` SSN.  Tests exercise this ordering.
_PATTERNS: tuple[_Pattern, ...] = (
    # ---- T1: highest sensitivity ----
    _Pattern(
        "ssn",
        "T1",
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        "[REDACTED-SSN]",
    ),
    _Pattern(
        "mrn",
        "T1",
        # Synthetic-data convention from CLAUDE.md rule 7: `GA-TEST-100001` style.
        # Also catches `MRN: 12345` and `MRN#12345`.
        re.compile(
            r"\b(?:MRN[-:#\s]*\d{4,}|GA-[A-Z]+-\d{4,})\b",
            re.IGNORECASE,
        ),
        "[REDACTED-MRN]",
    ),
    _Pattern(
        "credit_card",
        "T1",
        # 16-digit contiguous or grouped by 4s. Skips generic Luhn-check —
        # a demo detector, not a payment processor.
        re.compile(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b"),
        "[REDACTED-CC]",
    ),
    # ---- T2: high sensitivity ----
    _Pattern(
        "email",
        "T2",
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        "[REDACTED-EMAIL]",
    ),
    _Pattern(
        "phone",
        "T2",
        # US-shaped: optional +1, optional parens on area code, common separators.
        re.compile(
            r"\b(?:\+?1[-\s.]?)?(?:\(?\d{3}\)?[-\s.]?)\d{3}[-\s.]?\d{4}\b"
        ),
        "[REDACTED-PHONE]",
    ),
    _Pattern(
        "dob",
        "T2",
        re.compile(
            r"\b(?:0?[1-9]|1[0-2])[/-](?:0?[1-9]|[12]\d|3[01])[/-](?:19|20)\d{2}\b"
        ),
        "[REDACTED-DOB]",
    ),
    _Pattern(
        "street_address",
        "T2",
        re.compile(
            r"\b\d+\s+[A-Za-z][A-Za-z\s]*?"
            r"\b(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|"
            r"Lane|Ln|Drive|Dr|Court|Ct|Way|Place|Pl)\b\.?",
            re.IGNORECASE,
        ),
        "[REDACTED-ADDR]",
    ),
    # ---- T3: low sensitivity — tagged only, never mutated ----
    _Pattern(
        "zip",
        "T3",
        re.compile(r"\b\d{5}(?:-\d{4})?\b"),
        "[REDACTED-ZIP]",  # unused: T3 is never redacted, only tagged
    ),
)

_TIER_RANK = {"T1": 1, "T2": 2, "T3": 3, "T4": 4}
_REDACTION_MODE_VALUES = ("strict", "standard", "off")


class PHIRedactor(AIGateway):
    """AIGateway decorator that scans, tags, and (per mode) redacts PHI."""

    provider_name = "phi-redactor"

    def __init__(
        self,
        inner: AIGateway,
        *,
        mode: str | None = None,
    ):
        self._inner = inner
        self._mode = self._resolve_mode(mode)
        _logger.info("phi_redactor_initialized mode=%s", self._mode)

    @staticmethod
    def _resolve_mode(mode: str | None) -> str:
        if mode is None:
            mode = os.getenv("REDACTION_MODE", "strict").strip().lower()
        if mode not in _REDACTION_MODE_VALUES:
            raise ValueError(
                f"REDACTION_MODE must be one of {_REDACTION_MODE_VALUES}, got {mode!r}"
            )
        return mode

    def supports_tier(self, tier: Tier) -> bool:
        return self._inner.supports_tier(tier)

    async def complete(self, req: CompletionRequest) -> CompletionResponse:
        return await self._inner.complete(self._tag_and_redact(req))

    async def stream(self, req: CompletionRequest) -> AsyncIterator[str]:
        # Redact first; then delegate. Streaming the response back is unchanged —
        # the redactor does not scan the model output (that's a downstream
        # guardrail concern, not part of this delivery).
        redacted = self._tag_and_redact(req)
        async for chunk in self._inner.stream(redacted):
            yield chunk

    async def close(self) -> None:
        await self._inner.close()

    # ------------------------------------------------------------------ private

    def _tag_and_redact(self, req: CompletionRequest) -> CompletionRequest:
        """Return a new CompletionRequest with redacted messages + phi tags set.

        Idempotent: if the caller already tagged ``phi_present=True``, we still
        re-scan (defensive — the flag might have been fabricated). The returned
        request always reflects THIS scan's findings.
        """
        new_messages: list[Message] = []
        max_tier: str | None = None
        any_match = False
        for msg in req.messages:
            redacted_content, msg_tier, msg_hit = self._scan_content(msg.content)
            if msg_hit:
                any_match = True
                max_tier = _pick_higher_tier(max_tier, msg_tier)
            new_messages.append(
                Message(role=msg.role, content=redacted_content)
            )
        phi_tier = max_tier if any_match else None
        _logger.info(
            "phi_scan phi_present=%s phi_tier=%s mode=%s trace_id=%s",
            any_match,
            phi_tier,
            self._mode,
            req.trace_id,
        )
        return dataclasses.replace(
            req,
            messages=new_messages,
            phi_present=any_match,
            phi_tier=phi_tier,
        )

    def _scan_content(self, content: str) -> tuple[str, str | None, bool]:
        """Scan a single message's content.

        Returns ``(possibly_redacted_content, detected_tier_or_None, any_hit)``.
        In ``off`` mode the content is returned unchanged; in ``standard`` mode
        T2 is left in place. Detection reporting is independent of redaction —
        we always return the tier we saw, even if we didn't rewrite the string.

        NOTE: This function is the swap-in point for a Presidio-based detector.
        Return shape must be preserved: ``(str, tier|None, bool)``.
        """
        redacted = content
        detected: str | None = None
        for pat in _PATTERNS:
            if not pat.regex.search(redacted):
                continue
            detected = _pick_higher_tier(detected, pat.tier)
            if self._should_mutate(pat.tier):
                redacted = pat.regex.sub(pat.label, redacted)
        return redacted, detected, detected is not None

    def _should_mutate(self, tier: str) -> bool:
        if self._mode == "off":
            return False
        if self._mode == "standard":
            return tier == "T1"
        # strict
        return tier in ("T1", "T2")


def _pick_higher_tier(current: str | None, candidate: str) -> str:
    """Return whichever tier is more severe (lower numeric rank).

    Public-ish for tests. Not exported from the package.
    """
    if current is None:
        return candidate
    return current if _TIER_RANK[current] <= _TIER_RANK[candidate] else candidate
