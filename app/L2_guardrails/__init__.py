"""L2 Guardrails — middleware enforcing policy on every LLM call.

Phase 2 landing surface:
    - BAAGateGuard / BAAGateError (from .baa_gate)

Phase 2 remaining (not yet implemented):
    - PHI redactor (T1-T4 tiered)
    - Prompt-injection sentinel
    - Adversarial-verify wrapper (moved to Phase 7)

Design principle: every guardrail is itself an ``AIGateway``. They compose by
wrapping. `main.py` builds the middleware stack once at lifespan startup:
`Redactor(Sentinel(BAAGate(TieredAIGateway())))` — outermost guardrail runs first.
See ADR-0005.
"""
from .baa_gate import BAAGateError, BAAGateGuard

__all__ = ["BAAGateError", "BAAGateGuard"]
