"""L2 Guardrails — middleware enforcing policy on every LLM call.

Phase 2 landing surface:
    - BAAGateGuard / BAAGateError (from .baa_gate)
    - PHIRedactor (from .phi_redactor)
    - InjectionSentinel / InjectionSentinelError (from .injection_sentinel)

Phase 2 remaining (not yet implemented):
    - Adversarial-verify wrapper (moved to Phase 7)

Design principle: every guardrail is itself an ``AIGateway``. They compose by
wrapping. ``main.py`` builds the middleware stack once at lifespan startup:
``InjectionSentinel(PHIRedactor(BAAGateGuard(TieredAIGateway())), classifier=BAAGateGuard(TieredAIGateway()))``
— outermost guardrail runs first. See ADR-0005 (wrap-the-router), ADR-0006
(redactor-before-gate ordering + ``phi_present`` coupling), and ADR-0007
(sentinel outermost + hybrid regex/LLM detection + gate-wrapped classifier).
"""
from .baa_gate import BAAGateError, BAAGateGuard
from .injection_sentinel import InjectionSentinel, InjectionSentinelError
from .phi_redactor import PHIRedactor

__all__ = [
    "BAAGateError",
    "BAAGateGuard",
    "InjectionSentinel",
    "InjectionSentinelError",
    "PHIRedactor",
]
