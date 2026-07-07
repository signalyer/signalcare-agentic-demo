# ADR-0006 — L2 Middleware Ordering and the `phi_present` Coupling Contract

**Status:** Accepted
**Date:** 2026-07-07
**Deciders:** Solo founder

## Context

The Phase 2 delivery of `app/L2_guardrails/baa_gate.py` (ADR-0005, commit `d02b92a`) shipped with an unconditional-block behavior: any call to a vendor not on `APPROVED_PHI_VENDORS` was denied, regardless of whether the request actually carried PHI. Reading `docs/build-plan.md` line 25 more carefully surfaced a mismatch:

> `app/L2_guardrails/baa_gate.py` — middleware; refuses model calls with `phi_present=True` if vendor not in `APPROVED_PHI_VENDORS`

The specified behavior is **conditional on `phi_present=True`**, not unconditional. Non-PHI calls should flow to any vendor — that's the whole architectural point of tagging PHI at all. Build-plan line 34 reinforces this by naming the exact block-path test:

> Test: BAA gate blocks a request with `phi_present=True` and unapproved vendor

The strict interpretation the earlier commit shipped worked for a synthetic-data demo (both real vendors are on the allow-list, so nothing was ever denied in practice) but obscured the mechanism the architecture is meant to demonstrate: **PHI detection produces a signal; policy enforcement acts on that signal**. Without the signal, the enforcement is coarse and defensive; with it, the system can differentiate between "no PHI, any vendor is fine" and "PHI present, only BAA-covered vendors."

That signal has to come from somewhere. The build-plan lists `app/L2_guardrails/phi_redactor.py` as the next guardrail. Its job — scan message content, detect PHI, tag the request. Which raises two design questions this ADR resolves:

1. **Where does the `phi_present` tag live?** — inline on the `CompletionRequest`, on a sidecar object, on the router state, or somewhere else.
2. **In what order do the L2 guardrails run?** — redactor before gate, gate before redactor, or independent.

## Decision

**1. `phi_present: bool` and `phi_tier: str | None` are fields on `CompletionRequest`.** Frozen-dataclass fields with defaults (`False` / `None`) so existing callers compile without change. The redactor produces a new request via `dataclasses.replace(req, phi_present=..., phi_tier=..., messages=redacted)`. Downstream layers read the fields off the request as it flows through the middleware chain.

**2. The L2 middleware stack orders redactor OUTSIDE gate.** Runtime composition in `main.py`::

    router = TieredAIGateway()          # L6
    gated  = BAAGateGuard(router)       # L2  — reads phi_present
    stack  = PHIRedactor(gated)         # L2  — sets phi_present. Outermost.

`stack.complete(req)` calls `PHIRedactor.complete` first; the redactor scans, tags, and forwards a rewritten request to `BAAGateGuard.complete`, which then reads the tag and decides allow/deny. The tag is set exactly once per call, by exactly one component. The gate is the only reader; the redactor is the only writer.

**3. BAA gate enforcement rewrites from unconditional-block to conditional:**

- `req.phi_present is False` → forward to any vendor (approved or not).
- `req.phi_present is True` AND vendor in `APPROVED_PHI_VENDORS` → forward.
- `req.phi_present is True` AND vendor NOT in `APPROVED_PHI_VENDORS` → deny.

The `REQUIRE_BAA=false` short-circuit stays as-is (bypass everything).

**4. The redactor's absence is *safe* by default.** If a caller bypasses the redactor and calls the gate directly with `phi_present` unset, the default `False` means the gate allows. This is intentional defense-in-depth: the gate never *strengthens* enforcement past what the caller (or an upstream guardrail) explicitly claimed. Weakening the tag is the caller's choice; the gate does not re-classify. The whole-stack composition in `main.py` guarantees the redactor is always upstream in the runtime path.

## Consequences

### Positive

- **The architecture demo now shows the mechanism**, not just the outcome. An enterprise architect reading the code sees: content scanned → tag set → policy enforced on tag. Three concerns, three components, one clean coupling contract (the two request fields).
- **Non-PHI calls to unapproved vendors are now possible.** Which is the point of tagging PHI at all — if the answer was always "deny," we would not need a redactor.
- **Guardrails compose without cross-cuts.** The redactor does not know about the gate; the gate does not know about the redactor. They share only the request fields. Adding the injection sentinel next follows the same shape: another `AIGateway`-implementing decorator, wrapping the redactor, communicating (if it wants to) through additional request fields.
- **The `dataclasses.replace` pattern is idiomatic and honors the frozen-dataclass immutability property** established in `base.py`. The request is a stable snapshot at every layer of the chain.
- **The redactor is the only writer of `phi_present`.** Zero ambiguity about which component owns the tag.

### Negative

- **A caller who bypasses the redactor and hand-crafts a request with `phi_present=False` can get PHI content through to any vendor.** This is by design (see decision #4) but is worth naming. Mitigation: the whole-stack composition in `main.py` is the enforcement point; any code that constructs an `AIGateway` directly without wrapping in `PHIRedactor` is out of policy. Enforce at code review; a future ADR may add a runtime assertion that `main.py`'s stack is not swapped for a raw router.
- **Guard behavior changed under existing tests.** Denial-path tests in `test_baa_gate.py` had to be updated to explicitly set `phi_present=True`. Anyone reading commit history will see a behavior shift — that shift IS the fix, but a reviewer needs the ADR to understand the intent. Handled by writing this ADR alongside the code.
- **`CompletionRequest` gained two fields specific to L2 concerns.** This does bleed a bit of guardrail semantics into a lower-layer dataclass. Trade-off accepted: the alternative (a sidecar `RequestMetadata` object) would require every adapter and every guardrail to carry an extra argument through their method signatures, and would fragment the request-shape story. Inline fields are the simpler, testable, single-source-of-truth choice.

### Neutral / Notable

- **`phi_tier` is informational, not enforcement.** The BAA gate reads only `phi_present`. `phi_tier` is logged and available to downstream analytics, but no policy currently differentiates by tier. If we ever add tier-based policy (e.g., "T3 can go to any vendor, T1-T2 require approved"), it's an additive change to the gate's `_enforce` method — no signature change.
- **Idempotency.** The redactor re-scans every request even if `phi_present=True` is already set. A caller cannot fabricate the tag and expect the redactor to skip work. This is defensive against an accidental or malicious upstream that pre-sets fields.
- **The regex-based detector is a demo-shape stub.** Production PHI detection needs an NER-based classifier (Presidio is the swap-in path noted in the redactor's docstring). The `_scan_content` signature is the seam.
- **Redaction modes are policy, not detection.** The redactor always detects the same set of patterns; `REDACTION_MODE=strict|standard|off` only changes whether detected content is rewritten. `phi_present` and `phi_tier` are always set correctly regardless of mode. This matters because "detect but don't mutate" (mode=off) is a valid observability rollout — turn on detection, watch what gets tagged, THEN decide to redact.

## Alternatives Considered

- **Keep BAA gate unconditional (as shipped in ADR-0005).** Rejected — mismatches build-plan spec; obscures the architecture demo; the "why do we have a redactor if the gate always denies" question has no good answer.
- **Sidecar metadata object (`RequestMetadata(phi_present=..., ...)`) passed alongside the request.** Rejected — every adapter, guardrail, and future L3 agent would need to accept and forward two objects instead of one. Bleeds complexity across the entire codebase to keep two L2-specific booleans out of one dataclass.
- **Gate scans content itself (no redactor).** Rejected — collapses two concerns into one component; violates single-responsibility; makes the gate impossible to test without also testing the scanner; blocks a future NER swap-in.
- **Gate before redactor (redactor mutates content downstream of the block).** Rejected — the gate's whole job is to prevent PHI from reaching an unapproved vendor. Deciding the vendor before knowing whether PHI is present renders the check useless.
- **Redactor and gate as peers, orchestrated by a third "L2 controller" component.** Rejected — adds a component with no state to hold and no logic beyond calling two other components in order. That IS what the middleware wrapping pattern models more directly.
- **Add a `PHIRedactionMiddleware` at the FastAPI HTTP layer instead of at the AIGateway layer.** Rejected — same reason ADR-0005 rejected the FastAPI-Depends approach for BAA: not every LLM call comes through an HTTP endpoint. Future in-process callers (background workers, cron digest, evals) would bypass the redactor.

## References

- ADR-0005 (BAA Gate Wraps the Router) — supplies the wrap-the-router pattern this ADR reuses; ADR-0006 is what the earlier ADR's "future L2 guardrails compose the same way" statement anticipated.
- `docs/build-plan.md` line 25 — the specified `phi_present`-conditional behavior for the BAA gate.
- `docs/build-plan.md` line 34 — the exact block-path test name this ADR delivers.
- `ARCHITECTURE.md` L2 subgraph — the peer relationship between BAA gate, PHI redactor, and other L2 guardrails.
- `CLAUDE.md` non-negotiable rule 3 — "BAA gate is real middleware. Every LLM call passes through. No exceptions." Still upheld: every call passes through both guardrails; the change is *what enforcement is conditional on*, not whether it runs.
- Follow-on Phase 2 guardrail — `injection_sentinel.py` — slotted OUTSIDE `PHIRedactor` in the eventual stack, following the same shape.
