"""Unit tests for the L2 PHI redactor.

Offline. No live provider calls. Covers ADR-0006: redactor detects PHI at
T1-T4 tiers, sets ``phi_present`` + ``phi_tier`` on the outgoing request,
respects ``REDACTION_MODE``, and composes cleanly with the BAA gate to
produce the block-path build-plan line 34 requires.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from L2_guardrails import BAAGateError, BAAGateGuard, PHIRedactor
from L2_guardrails.phi_redactor import _pick_higher_tier
from L6_adapters.ai_gateway import (
    AIGateway,
    CompletionRequest,
    CompletionResponse,
    Message,
    Tier,
)


class _CapturingRouter(AIGateway):
    """Records the request it received so tests can inspect post-redaction state."""

    provider_name = "capturing-router"

    def __init__(self, vendor: str = "capturing-router"):
        self._vendor = vendor
        self.received: list[CompletionRequest] = []
        self.closed = False

    def supports_tier(self, tier: Tier) -> bool:  # noqa: ARG002
        return True

    def vendor_for(self, tier: Tier) -> str:  # noqa: ARG002
        return self._vendor

    async def complete(self, req: CompletionRequest) -> CompletionResponse:
        self.received.append(req)
        return CompletionResponse(
            text="ok",
            model=f"{self._vendor}-model",
            provider=self._vendor,
            tokens_in=0,
            tokens_out=0,
            latency_ms=0,
            trace_id=req.trace_id,
        )

    async def stream(self, req: CompletionRequest) -> AsyncIterator[str]:
        self.received.append(req)
        for piece in ("x", "y", "z"):
            yield piece

    async def close(self) -> None:
        self.closed = True


def _req(content: str, tier: Tier = Tier.BALANCED) -> CompletionRequest:
    return CompletionRequest(
        tier=tier,
        messages=[Message(role="user", content=content)],
        trace_id="tr-redact",
    )


class TestT1Detection:
    async def test_ssn_detected_and_redacted_in_strict(self):
        router = _CapturingRouter()
        redactor = PHIRedactor(router, mode="strict")
        await redactor.complete(_req("Patient SSN is 123-45-6789 on file."))
        forwarded = router.received[0]
        assert forwarded.phi_present is True
        assert forwarded.phi_tier == "T1"
        assert "123-45-6789" not in forwarded.messages[0].content
        assert "[REDACTED-SSN]" in forwarded.messages[0].content

    async def test_mrn_synthetic_convention(self):
        # Project synthetic-data convention: GA-TEST-100001 style.
        router = _CapturingRouter()
        redactor = PHIRedactor(router, mode="strict")
        await redactor.complete(_req("MRN GA-TEST-100001 needs follow-up."))
        forwarded = router.received[0]
        assert forwarded.phi_present is True
        assert forwarded.phi_tier == "T1"
        assert "GA-TEST-100001" not in forwarded.messages[0].content

    async def test_mrn_colon_form(self):
        router = _CapturingRouter()
        redactor = PHIRedactor(router, mode="strict")
        await redactor.complete(_req("Chart MRN: 8842991 pending review."))
        assert router.received[0].phi_tier == "T1"

    async def test_credit_card(self):
        router = _CapturingRouter()
        redactor = PHIRedactor(router, mode="strict")
        await redactor.complete(_req("Card 4111 1111 1111 1111 on file"))
        forwarded = router.received[0]
        assert forwarded.phi_tier == "T1"
        assert "[REDACTED-CC]" in forwarded.messages[0].content


class TestT2Detection:
    async def test_email_and_phone_together_max_tier_t2(self):
        router = _CapturingRouter()
        redactor = PHIRedactor(router, mode="strict")
        await redactor.complete(
            _req("Contact john@example.com or (555) 123-4567.")
        )
        forwarded = router.received[0]
        assert forwarded.phi_present is True
        assert forwarded.phi_tier == "T2"
        content = forwarded.messages[0].content
        assert "john@example.com" not in content
        assert "555" not in content  # phone redacted
        assert "[REDACTED-EMAIL]" in content
        assert "[REDACTED-PHONE]" in content

    async def test_dob(self):
        router = _CapturingRouter()
        redactor = PHIRedactor(router, mode="strict")
        await redactor.complete(_req("DOB 03/15/1978 per intake form."))
        forwarded = router.received[0]
        assert forwarded.phi_tier == "T2"
        assert "03/15/1978" not in forwarded.messages[0].content

    async def test_street_address(self):
        router = _CapturingRouter()
        redactor = PHIRedactor(router, mode="strict")
        await redactor.complete(_req("Lives at 123 Main Street, Atlanta."))
        forwarded = router.received[0]
        assert forwarded.phi_tier == "T2"
        assert "Main Street" not in forwarded.messages[0].content


class TestT4PassThrough:
    async def test_clean_prompt_passes_untouched(self):
        router = _CapturingRouter()
        redactor = PHIRedactor(router, mode="strict")
        await redactor.complete(
            _req("Summarize the referral intake workflow in one paragraph.")
        )
        forwarded = router.received[0]
        assert forwarded.phi_present is False
        assert forwarded.phi_tier is None
        assert (
            forwarded.messages[0].content
            == "Summarize the referral intake workflow in one paragraph."
        )


class TestTierPrecedenceAcrossMessages:
    async def test_max_tier_wins_across_messages(self):
        # One message has T2 (email), another has T1 (SSN). phi_tier must be T1.
        router = _CapturingRouter()
        redactor = PHIRedactor(router, mode="strict")
        req = CompletionRequest(
            tier=Tier.BALANCED,
            messages=[
                Message(role="user", content="Contact foo@bar.com."),
                Message(role="user", content="SSN 999-88-7777."),
            ],
            trace_id="tr",
        )
        await redactor.complete(req)
        assert router.received[0].phi_tier == "T1"


class TestRedactionModes:
    async def test_standard_leaves_t2_but_redacts_t1(self):
        router = _CapturingRouter()
        redactor = PHIRedactor(router, mode="standard")
        await redactor.complete(
            _req("SSN 111-22-3333 and email a@b.co in one line.")
        )
        forwarded = router.received[0]
        # Tags reflect the highest detected tier regardless of mode.
        assert forwarded.phi_tier == "T1"
        content = forwarded.messages[0].content
        # T1 redacted, T2 email left in place.
        assert "111-22-3333" not in content
        assert "a@b.co" in content

    async def test_off_tags_but_does_not_mutate(self):
        router = _CapturingRouter()
        redactor = PHIRedactor(router, mode="off")
        original = "SSN 111-22-3333 stays as-is in OFF mode."
        await redactor.complete(_req(original))
        forwarded = router.received[0]
        assert forwarded.phi_present is True
        assert forwarded.phi_tier == "T1"
        assert forwarded.messages[0].content == original

    def test_invalid_mode_rejected_at_construction(self):
        with pytest.raises(ValueError):
            PHIRedactor(_CapturingRouter(), mode="quiet")


class TestEnvConfig:
    def test_mode_from_env(self, monkeypatch):
        monkeypatch.setenv("REDACTION_MODE", "STANDARD")  # case-insensitive
        redactor = PHIRedactor(_CapturingRouter())
        assert redactor._mode == "standard"  # noqa: SLF001

    def test_default_mode_is_strict(self, monkeypatch):
        monkeypatch.delenv("REDACTION_MODE", raising=False)
        redactor = PHIRedactor(_CapturingRouter())
        assert redactor._mode == "strict"  # noqa: SLF001


class TestStreamAlsoRedacts:
    async def test_streaming_uses_redacted_request(self):
        router = _CapturingRouter()
        redactor = PHIRedactor(router, mode="strict")
        chunks = [c async for c in redactor.stream(_req("SSN 111-22-3333"))]
        assert "".join(chunks) == "xyz"
        # The router saw a REDACTED request even for streaming.
        assert router.received[0].phi_present is True
        assert "111-22-3333" not in router.received[0].messages[0].content


class TestDelegation:
    async def test_close_delegated(self):
        router = _CapturingRouter()
        redactor = PHIRedactor(router, mode="strict")
        await redactor.close()
        assert router.closed


class TestComposedWithBAAGate:
    """End-to-end: PHIRedactor(BAAGateGuard(Router)). Proves the phi_present
    tag flows from redactor into gate and produces the correct decision."""

    async def test_unapproved_vendor_plus_phi_blocks(self):
        # build-plan line 34: BAA gate blocks phi_present=True + unapproved vendor.
        router = _CapturingRouter(vendor="rogue-cloud")
        gated = BAAGateGuard(
            router,
            require_baa=True,
            approved_vendors=frozenset({"anthropic", "ollama"}),
        )
        redactor = PHIRedactor(gated, mode="strict")
        with pytest.raises(BAAGateError) as exc_info:
            await redactor.complete(_req("Patient SSN 555-11-2222 needs auth."))
        assert exc_info.value.vendor == "rogue-cloud"
        assert len(router.received) == 0  # nothing reached the router

    async def test_unapproved_vendor_no_phi_allowed(self):
        # No PHI in prompt → gate lets the call through even though vendor
        # is unapproved. This is the whole point of the phi_present tag.
        router = _CapturingRouter(vendor="rogue-cloud")
        gated = BAAGateGuard(
            router,
            require_baa=True,
            approved_vendors=frozenset({"anthropic", "ollama"}),
        )
        redactor = PHIRedactor(gated, mode="strict")
        resp = await redactor.complete(_req("Summarize the demo architecture."))
        assert resp.provider == "rogue-cloud"
        assert router.received[0].phi_present is False

    async def test_approved_vendor_with_phi_forwards_redacted(self):
        router = _CapturingRouter(vendor="anthropic")
        gated = BAAGateGuard(
            router,
            require_baa=True,
            approved_vendors=frozenset({"anthropic"}),
        )
        redactor = PHIRedactor(gated, mode="strict")
        await redactor.complete(_req("SSN 111-22-3333"))
        forwarded = router.received[0]
        assert forwarded.phi_present is True
        assert "111-22-3333" not in forwarded.messages[0].content


class TestTierRanking:
    """The internal _pick_higher_tier helper — small, but load-bearing."""

    def test_first_wins_when_none(self):
        assert _pick_higher_tier(None, "T3") == "T3"

    def test_t1_beats_t2(self):
        assert _pick_higher_tier("T2", "T1") == "T1"
        assert _pick_higher_tier("T1", "T2") == "T1"

    def test_t2_beats_t3(self):
        assert _pick_higher_tier("T3", "T2") == "T2"
