# ADR-0005 — BAA Gate Wraps the Router, Not Individual Adapters

**Status:** Accepted
**Date:** 2026-07-07
**Deciders:** Solo founder

## Context

Phase 2 begins with `app/L2_guardrails/baa_gate.py` — the middleware that enforces the project rule "every LLM call passes through the BAA gate. No exceptions." (`CLAUDE.md` non-negotiable rule 3.) The gate's job is to reject any request whose target vendor is not on the `APPROVED_PHI_VENDORS` allow-list, and to do so *before* the request payload leaves the process.

The BAA gate must satisfy three constraints:

1. **Wraps every LLM call, not some of them.** No matter which agent, which tier, or which future adapter gets added — every call must flow through the gate.
2. **Preserves the ADR-0002 abstraction.** Callers upstream (`main.py`, future L3 agents) already talk to `TieredAIGateway` as an `AIGateway`. The gate must not change that contract.
3. **Fails typed and observable.** A rejected call must raise a distinct exception the API boundary can map to HTTP 451, and every decision (allow or deny) must log with a `trace_id`.

The design choice is *where* the gate lives relative to the existing gateway stack. Two candidates:

- **(A) Wrap the router (`TieredAIGateway`).** One `BAAGateGuard` instance that itself implements `AIGateway` by delegating to an inner router.
- **(B) Wrap each concrete adapter (`OllamaGateway`, `AnthropicGateway`, and every future one).** Each adapter is decorated at construction time in the router or at app startup.

## Decision

**Wrap the router.** The gate is a single `BAAGateGuard(AIGateway)` that composes over `TieredAIGateway`. All calls upstream — `agents/echo`, future L3 agents, future orchestrator — hold a `BAAGateGuard` typed as `AIGateway` and never learn there's a guard in the chain other than by receiving a `BAAGateError` on denial.

Vendor identity is resolved by a new `TieredAIGateway.vendor_for(tier: Tier) -> str` method that returns the `provider_name` of the concrete adapter the router would dispatch to. The guard calls `inner.vendor_for(req.tier)` before delegating `complete`/`stream`.

`BAAGateError` inherits from `Exception` (not `AIGatewayError`) so that the existing `except AIGatewayError` handlers in agent endpoints do NOT swallow denials as generic 502 gateway errors. A FastAPI exception handler in `main.py` maps `BAAGateError` to HTTP 451 (Unavailable For Legal Reasons).

## Consequences

### Positive

- **One gate to reason about.** Adding a fourth adapter (or removing one) does not require re-wiring N gate wrappers. The router changes; the guard is untouched.
- **The abstraction is preserved and *strengthened*.** Upstream code still receives an `AIGateway`. The guard is invisible until it fires, which is exactly the behavior a middleware layer should have.
- **Vendor resolution stays inside the router**, where the tier-to-adapter mapping already lives. The guard doesn't duplicate dispatch logic — it asks the router "who would you route this to?" and enforces on the answer.
- **Testable in isolation.** A test can inject a fake router with a controlled `vendor_for` and verify allow/deny/trace-id behavior without touching real providers.
- **Consistent with future L2 guardrails.** PHI redactor and injection sentinel (Phase 2 tasks 2 and 3) will follow the same wrap-the-router shape, forming a middleware stack: `Redactor(Sentinel(BAAGate(Router)))`. Each layer independent, each an `AIGateway`.

### Negative

- **Per-provider policy is not first-class.** If we ever needed a policy like "Anthropic requires a BAA header on the outgoing HTTP call itself, but Ollama does not" — that would live inside the individual concrete adapters, not the guard. The guard is coarser-grained: allow or deny by vendor name. Trade-off accepted: no such per-provider policy exists today or in the Phase 2-8 plan; adding it later means moving *that specific* concern into the adapter, not re-doing the guard.
- **The router grew a method (`vendor_for`)** that's outside the abstract base's contract. It's a router-specific concern (only routers dispatch). Guard is typed to `TieredAIGateway`, not generic `AIGateway`. Acceptable coupling — the guard is *of* the router; it's not a general-purpose wrapper.

### Neutral / Notable

- **`BAAGateError` deliberately does not inherit from `AIGatewayError`.** This is a semantic choice: an AI gateway *error* (network failure, provider outage) is a transient issue callers may retry; a BAA gate denial is a policy decision the caller must never bypass. Different failure classes deserve different exception types and different HTTP codes (502 vs 451).
- **`.env` semantics changed.** `REQUIRE_BAA` default flipped from `false` to `true` in `.env.example`; `APPROVED_PHI_VENDORS` default seeded with `anthropic,ollama`. Rationale: rule 3 says the BAA gate is real middleware, not a stub. Shipping with the default `false` would ship the middleware disabled, which contradicts the rule.
- **The demo's block-path is provable.** Unit tests inject a mock router that reports an unapproved vendor and assert `BAAGateError` is raised — proving the gate actually blocks, not just wraps. Runtime path with real adapters stays clean (both real vendors are approved).

## Alternatives Considered

- **Wrap each concrete adapter (Option B).** Rejected: multiplies wrap sites by adapter count; every new adapter must remember to be wrapped; error-prone as the catalog grows in Phase 3.
- **Put BAA enforcement inside `TieredAIGateway.complete/stream` directly** (no separate guard class). Rejected: violates single-responsibility. `TieredAIGateway` dispatches by tier; that's it. Mixing in policy enforcement makes the router a policy engine and breaks the ADR-0002 "skinny router" property.
- **FastAPI dependency (`Depends(baa_check)`) at endpoint level.** Rejected: only enforces at HTTP boundaries. Future in-process callers (background workers, cron digests, evals) would bypass it. The rule is "every LLM call," not "every HTTP-served LLM call."
- **Decorator on `complete`/`stream` methods (Python `@baa_gate` on adapter methods).** Rejected: same problem as B — requires every concrete adapter author to remember to apply it. Wrapping-a-composite is safer than decorating-N-methods.
- **Environment variable `BAA_GATE_ENABLED` with runtime toggle only** (no code guard, just an env check inside adapters). Rejected: entangles policy with implementation and gives no place to hang the trace-id/log discipline required by rule 3.

## References

- ADR-0002 (Cloud-Agnostic Adapter Pattern) — this ADR wraps its output; does not amend it
- ADR-0004 (Direct Anthropic SDK) — supplies the current concrete adapters this ADR gates
- `CLAUDE.md` non-negotiable rule 3 — "BAA gate is real middleware. Every LLM call passes through `app/L2_guardrails/baa_gate.py`. No exceptions."
- HTTP 451 (Unavailable For Legal Reasons) — RFC 7725
- Follow-on Phase 2 guardrails that adopt the same wrap-the-router shape: `phi_redactor.py`, `injection_sentinel.py`
