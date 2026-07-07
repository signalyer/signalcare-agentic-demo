"""Unit tests for the L2 BAA gate.

Offline. No live provider calls. A ``_FakeRouter`` stands in for ``TieredAIGateway``
so tests can control which vendor a request would be routed to and verify allow/
deny/trace-id behavior without touching real adapters.

Covers ADR-0005: guard wraps the router, denies unapproved vendors with a typed
``BAAGateError`` carrying the ``trace_id``, and delegates interface methods.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from L2_guardrails import BAAGateError, BAAGateGuard
from L6_adapters.ai_gateway import (
    AIGateway,
    CompletionRequest,
    CompletionResponse,
    Message,
    Tier,
)


class _FakeRouter(AIGateway):
    """Stand-in for TieredAIGateway with a controllable vendor_for and call counters.

    Not a real router — just enough to exercise BAAGateGuard's contract.
    """

    provider_name = "fake-router"

    def __init__(self, vendor: str, supported: set[Tier] | None = None):
        self._vendor = vendor
        self._supported = supported or {Tier.FAST, Tier.BALANCED, Tier.REASONING}
        self.complete_calls: list[CompletionRequest] = []
        self.stream_calls: list[CompletionRequest] = []
        self.closed = False

    def supports_tier(self, tier: Tier) -> bool:
        return tier in self._supported

    def vendor_for(self, tier: Tier) -> str:  # noqa: ARG002 — vendor is fixed for the fake
        return self._vendor

    async def complete(self, req: CompletionRequest) -> CompletionResponse:
        self.complete_calls.append(req)
        return CompletionResponse(
            text="ok",
            model=f"{self._vendor}-model",
            provider=self._vendor,
            tokens_in=1,
            tokens_out=1,
            latency_ms=1,
            trace_id=req.trace_id,
        )

    async def stream(self, req: CompletionRequest) -> AsyncIterator[str]:
        self.stream_calls.append(req)
        for piece in ("a", "b", "c"):
            yield piece

    async def close(self) -> None:
        self.closed = True


def _req(
    tier: Tier = Tier.BALANCED,
    trace: str = "tr-baa",
    *,
    phi_present: bool = False,
    phi_tier: str | None = None,
) -> CompletionRequest:
    """Build a CompletionRequest. Default is no-PHI; denial-path tests pass
    ``phi_present=True`` since the gate is conditional on it (ADR-0006)."""
    return CompletionRequest(
        tier=tier,
        messages=[Message(role="user", content="ping")],
        trace_id=trace,
        phi_present=phi_present,
        phi_tier=phi_tier,
    )


class TestAllow:
    async def test_approved_vendor_passes_through(self):
        router = _FakeRouter(vendor="anthropic")
        guard = BAAGateGuard(
            router,
            require_baa=True,
            approved_vendors=frozenset({"anthropic", "ollama"}),
        )
        resp = await guard.complete(_req(Tier.BALANCED))
        assert resp.text == "ok"
        assert len(router.complete_calls) == 1

    async def test_approved_case_insensitive(self):
        # Adapter reports "Anthropic" but allow-list has "anthropic" — must still allow.
        router = _FakeRouter(vendor="Anthropic")
        guard = BAAGateGuard(
            router,
            require_baa=True,
            approved_vendors=frozenset({"anthropic"}),
        )
        await guard.complete(_req())
        assert len(router.complete_calls) == 1

    async def test_require_baa_false_bypasses_check(self):
        # With REQUIRE_BAA=false, even an unapproved vendor is forwarded.
        router = _FakeRouter(vendor="unapproved-vendor")
        guard = BAAGateGuard(
            router,
            require_baa=False,
            approved_vendors=frozenset(),
        )
        resp = await guard.complete(_req())
        assert resp.provider == "unapproved-vendor"
        assert len(router.complete_calls) == 1


class TestDeny:
    """Denial-path tests. All requests have ``phi_present=True`` — the gate is
    conditional on the flag per ADR-0006, so a no-PHI call to an unapproved
    vendor is allowed by design (see ``TestConditional`` below)."""

    async def test_unapproved_vendor_with_phi_raises_typed_error(self):
        router = _FakeRouter(vendor="rogue-cloud")
        guard = BAAGateGuard(
            router,
            require_baa=True,
            approved_vendors=frozenset({"anthropic", "ollama"}),
        )
        with pytest.raises(BAAGateError) as exc_info:
            await guard.complete(_req(phi_present=True, phi_tier="T1"))
        assert exc_info.value.vendor == "rogue-cloud"
        # Router.complete must NOT have been called on a denial.
        assert len(router.complete_calls) == 0

    async def test_denial_carries_trace_id(self):
        router = _FakeRouter(vendor="rogue-cloud")
        guard = BAAGateGuard(
            router,
            require_baa=True,
            approved_vendors=frozenset({"anthropic"}),
        )
        with pytest.raises(BAAGateError) as exc_info:
            await guard.complete(_req(trace="tr-XYZ", phi_present=True, phi_tier="T2"))
        assert exc_info.value.trace_id == "tr-XYZ"

    async def test_baa_gate_error_is_not_ai_gateway_error(self):
        # ADR-0005: denials must not be caught by `except AIGatewayError`.
        from L6_adapters.ai_gateway import AIGatewayError

        assert not issubclass(BAAGateError, AIGatewayError)

    async def test_empty_allow_list_denies_phi_calls(self):
        router = _FakeRouter(vendor="anthropic")
        guard = BAAGateGuard(
            router,
            require_baa=True,
            approved_vendors=frozenset(),
        )
        with pytest.raises(BAAGateError):
            await guard.complete(_req(phi_present=True, phi_tier="T1"))

    async def test_stream_is_gated_before_bytes_leave(self):
        router = _FakeRouter(vendor="rogue-cloud")
        guard = BAAGateGuard(
            router,
            require_baa=True,
            approved_vendors=frozenset({"anthropic"}),
        )
        with pytest.raises(BAAGateError):
            # Consuming even one chunk must raise — the guard enforces before opening
            # the upstream stream.
            async for _ in guard.stream(_req(phi_present=True, phi_tier="T1")):
                pytest.fail("stream yielded a chunk on a denied call")
        assert len(router.stream_calls) == 0


class TestConditional:
    """The phi_present coupling with the redactor (ADR-0006). A no-PHI call is
    forwarded regardless of vendor approval; PHI requires an approved vendor."""

    async def test_no_phi_allows_unapproved_vendor(self):
        # This is the build-plan's implicit permissive path — a non-PHI call
        # goes to any vendor without gate interference.
        router = _FakeRouter(vendor="some-random-vendor")
        guard = BAAGateGuard(
            router,
            require_baa=True,
            approved_vendors=frozenset({"anthropic"}),
        )
        resp = await guard.complete(_req(phi_present=False))
        assert resp.provider == "some-random-vendor"
        assert len(router.complete_calls) == 1

    async def test_phi_true_and_unapproved_blocks(self):
        # build-plan line 34: "BAA gate blocks a request with phi_present=True
        # and unapproved vendor." The canonical block-path.
        router = _FakeRouter(vendor="rogue-cloud")
        guard = BAAGateGuard(
            router,
            require_baa=True,
            approved_vendors=frozenset({"anthropic", "ollama"}),
        )
        with pytest.raises(BAAGateError):
            await guard.complete(_req(phi_present=True, phi_tier="T1"))

    async def test_phi_true_and_approved_forwards(self):
        router = _FakeRouter(vendor="anthropic")
        guard = BAAGateGuard(
            router,
            require_baa=True,
            approved_vendors=frozenset({"anthropic", "ollama"}),
        )
        resp = await guard.complete(_req(phi_present=True, phi_tier="T2"))
        assert resp.provider == "anthropic"


class TestDelegation:
    async def test_supports_tier_delegated(self):
        router = _FakeRouter(vendor="anthropic", supported={Tier.BALANCED})
        guard = BAAGateGuard(
            router,
            require_baa=True,
            approved_vendors=frozenset({"anthropic"}),
        )
        assert guard.supports_tier(Tier.BALANCED)
        assert not guard.supports_tier(Tier.FAST)

    async def test_close_delegated(self):
        router = _FakeRouter(vendor="anthropic")
        guard = BAAGateGuard(
            router,
            require_baa=True,
            approved_vendors=frozenset({"anthropic"}),
        )
        await guard.close()
        assert router.closed


class TestEnvConfig:
    """Guard config resolves from env when not injected."""

    def test_env_true_and_seeded_allow_list(self, monkeypatch):
        monkeypatch.setenv("REQUIRE_BAA", "true")
        monkeypatch.setenv("APPROVED_PHI_VENDORS", "anthropic, Ollama ,")
        router = _FakeRouter(vendor="anthropic")
        guard = BAAGateGuard(router)
        assert guard._require_baa is True  # noqa: SLF001 — invariant check
        # Whitespace stripped, case-normalized, empty entries dropped.
        assert guard._approved == frozenset({"anthropic", "ollama"})  # noqa: SLF001

    def test_env_false_disables_enforcement(self, monkeypatch):
        monkeypatch.setenv("REQUIRE_BAA", "false")
        monkeypatch.setenv("APPROVED_PHI_VENDORS", "")
        router = _FakeRouter(vendor="anything")
        guard = BAAGateGuard(router)
        assert guard._require_baa is False  # noqa: SLF001
