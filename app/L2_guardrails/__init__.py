"""L2 Guardrails — middleware enforcing policy on every LLM call.

Phase 2 landing surface:
    - BAAGateGuard / BAAGateError (from .baa_gate)
    - PHIRedactor (from .phi_redactor)

Phase 2 remaining (not yet implemented):
    - Prompt-injection sentinel
    - Adversarial-verify wrapper (moved to Phase 7)

Design principle: every guardrail is itself an ``AIGateway``. They compose by
wrapping. ``main.py`` builds the middleware stack once at lifespan startup:
``PHIRedactor(BAAGateGuard(TieredAIGateway()))`` — outermost guardrail runs
first. See ADR-0005 (wrap-the-router) and ADR-0006 (redactor-before-gate
ordering + ``phi_present`` coupling).
"""
from .baa_gate import BAAGateError, BAAGateGuard
from .phi_redactor import PHIRedactor

__all__ = ["BAAGateError", "BAAGateGuard", "PHIRedactor"]
