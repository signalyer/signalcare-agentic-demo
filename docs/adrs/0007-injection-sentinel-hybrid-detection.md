# ADR-0007 — Injection Sentinel: Hybrid Regex + LLM Detection, Outermost L2 Wrap

**Status:** Accepted
**Date:** 2026-07-07
**Deciders:** Solo founder

## Context

Build-plan line 27 specifies a Phase 2 deliverable at `app/L2_guardrails/injection_sentinel.py`:

> Middleware that inspects user-authored content for prompt-injection attempts (jailbreaks, role overrides, system-prompt extraction, obfuscated payloads) and blocks or flags per policy.

This is the third L2 guardrail. ADR-0005 established the wrap-the-router pattern; ADR-0006 established the redactor-before-gate ordering plus the `phi_present` coupling contract. The sentinel is the next decorator on the stack.

The handoff from the prior session (`docs/handoffs/2026-07-07-phase2-tasks-1-2-to-injection-sentinel.md`) surfaced three alternatives for the detector:

- (a) Regex only — fast, offline, zero API cost, deterministic.
- (b) LLM classifier only — highest recall on novel attacks, adds 100–500 ms + Ollama dependency to every call.
- (c) Hybrid — regex first, LLM fallback for ambiguous or novel-looking content.

The decision-carrying question then became: what does "hybrid" mean concretely — and how does an LLM classifier compose with the L2 stack it is itself a member of, without recursion and without bypassing the BAA gate that `CLAUDE.md` rule 3 mandates for *every* LLM call?

Four sub-questions this ADR resolves:

1. **What triggers the LLM branch?** — always, or only when a cheap signal suggests the request is worth an LLM look.
2. **How does the classifier compose with the L2 stack?** — direct router handle, gate-wrapped handle, or the full outermost stack.
3. **What is the failure mode of the classifier?** — fail-open (log and allow), or fail-closed (block on classifier error).
4. **Which HTTP status does `InjectionSentinelError` map to?** — 400, 403, or 422.

## Decision

**1. Composition — sentinel is the outermost L2 wrap.** Runtime stack in `main.py` lifespan:

    router     = TieredAIGateway()                          # L6
    gated      = BAAGateGuard(router)                       # L2 — reads phi_present
    redacted   = PHIRedactor(gated)                         # L2 — sets phi_present
    stack      = InjectionSentinel(redacted, classifier=gated)  # L2 — outermost
    app.state.ai_gateway = stack

The sentinel runs *first*, before the redactor and before the gate. Rationale: an injection attempt should die before it consumes redactor + gate + router work, and the sentinel needs to see the *unmutated* user content (redactor would scrub PHI-shaped payloads that could carry disguised injection instructions).

**2. Detection pipeline — regex-first, heuristic-gated LLM fallback.**

For each `req.messages` entry with `role == "user"`:

    a. Run the regex pass against ~10 known-injection patterns.
       Any hit → detected = True, source = "regex", exit.
    b. Regex miss + at least one "suspicion keyword" in the user content
       → route the message to the injected `classifier` gateway (Fast tier).
       Classifier returns JSON {is_injection, confidence, reason}.
       If confidence >= SENTINEL_LLM_THRESHOLD → detected = True, source = "llm".
    c. Regex miss + no suspicion keyword → allow without LLM call.

System messages are NOT scanned. Injection is a trust-boundary attack; system content is developer-authored (trusted source), user content is caller-authored (untrusted source). Scanning system messages produces false positives — developers legitimately write "ignore the following context" style instructions that would trigger jailbreak patterns.

**3. Suspicion keywords (heuristic trigger for the LLM branch).** Case-insensitive substring match; any hit routes the message to the classifier:

    ignore, instructions, system prompt, override, reveal, disclose,
    role of, act as, you are now, pretend, developer mode, jailbreak,
    prior message, previous message

These keywords exist to *save* Ollama calls on obviously benign traffic ("What is Mrs. Sanchez's next appointment?") — not as a second detector layer. The set errs toward recall (letting more calls through to the LLM) rather than precision. False positives waste an Ollama call but do not produce a false block.

**4. Classifier gateway — reuse the BAA gate wrap, skip the redactor and the sentinel itself.** The sentinel constructor takes `classifier: AIGateway | None`. In production wiring `main.py` passes the same `BAAGateGuard(TieredAIGateway())` handle it uses as the inner-of-redactor. Three consequences:

- No recursion. The classifier call bypasses the sentinel, so it cannot re-enter itself.
- No redactor mutation. The classifier receives the *raw* user content and can spot obfuscated attacks the redactor would scrub away.
- The BAA gate still runs on the classifier call. `CLAUDE.md` rule 3 is upheld — *every* LLM call passes through the gate.

**5. Defensive PHI tagging on classifier calls.** The sentinel constructs the classifier `CompletionRequest` with `phi_present=True, phi_tier=None`. Rationale: the classifier is asked to examine *unredacted* user content that may or may not contain PHI. Without this tag, the BAA gate would default-allow the call to any vendor (regardless of whether it holds a BAA). Setting the flag defensively forces the classifier to hit an approved vendor — Ollama is on the default `APPROVED_PHI_VENDORS` list, so the Fast tier resolves cleanly. If an operator removes Ollama from that list, the classifier call fails; the sentinel falls back to regex-only (see fail-open policy below).

**6. Fail-open on classifier error.** If the LLM branch raises anything — `AIGatewayError`, `BAAGateError`, timeout, JSON parse failure, Ollama unreachable — the sentinel logs a WARN with the trace_id and treats the message as *not detected*. Rationale:

- The regex pass already caught known-bad. Fail-open degrades to regex-only.
- Fail-closed would let a single Ollama outage block *every* request. That is a self-DoS.
- Enterprise architects reviewing this can turn on fail-closed with a config flag later if the observability data warrants it. Defaults are conservative-toward-availability for a Phase 2 demo.

**7. Modes — `SENTINEL_MODE=block|flag|off`.** Analogous to `REDACTION_MODE`. Env resolved once at guard construction.

- `block` (default): raise `InjectionSentinelError` → HTTP 400.
- `flag`: log WARN with source (regex/llm) and pattern name, forward the request untouched. Observability-first rollout; frontend/audit can surface the flag from logs.
- `off`: skip detection entirely; forward. Escape hatch for load tests and demos where the sentinel path is not under test.

**8. Exception hierarchy — `InjectionSentinelError(Exception)`.** NOT a subclass of `AIGatewayError`, following the same rationale as `BAAGateError` in ADR-0005: injection block is a *policy decision*; `AIGatewayError` is a *transient failure*. Different failure classes, different HTTP codes, different retry semantics.

**9. HTTP mapping — `InjectionSentinelError` → 400 Bad Request.** The malformed component is the request payload itself (adversarial content). 400 says "we will not process this content" without leaking policy detail to a probing attacker. `main.py` registers a FastAPI exception handler mirroring the BAA gate handler, returning a JSON body with `error`, `detail`, `source` (regex/llm), `pattern` (regex name or "llm-classifier"), and `trace_id`.

**10. Env vars introduced.**

- `SENTINEL_MODE` — `block` | `flag` | `off`. Default: `block`.
- `SENTINEL_LLM_THRESHOLD` — float 0.0–1.0. Confidence threshold above which the LLM verdict flips detection to true. Default: `0.7`.

`SENTINEL_LLM_ENABLED` is intentionally NOT introduced. Enabling/disabling the LLM branch is a *constructor* concern (pass `classifier=None`) not a runtime concern. Tests pass `None`; production wires the gated gateway.

## Consequences

### Positive

- **Latency budget respected on the common path.** Benign traffic (no regex hit, no suspicion keyword) skips the LLM branch entirely — zero added latency. Regex+heuristic is O(µs).
- **Novel-attack coverage without an always-on LLM tax.** The heuristic gate lets a small suspect subset consume Ollama; the majority of requests pay only for the regex pass.
- **`CLAUDE.md` rule 3 is upheld transitively.** The classifier's own LLM call flows through the BAA gate. There is no "internal" LLM call that bypasses policy.
- **No recursion.** The classifier's `AIGateway` handle is the gate-wrapped router — the sentinel itself is not in that handle's chain. The composition asymmetry is explicit and documented in constructor arguments.
- **Fail-open preserves demo reliability.** Ollama being down does not turn the demo into a wall of 400s.
- **Tests do not need Ollama running.** Passing `classifier=None` disables the LLM branch entirely; regex-only tests are the same shape as the redactor/gate tests. A separate integration test can exercise the classifier path with a stub `AIGateway`.

### Negative

- **Two calls in the worst case.** A regex miss + suspicion keyword + LLM verdict = one classifier RPC on top of the eventual downstream call. Latency: ~50–200 ms Ollama classification + downstream. Acceptable for a demo, worth revisiting under real load.
- **The heuristic keyword list is itself a policy surface.** A caregiver typing "ignore my last message about Tuesday's appointment" will trip the LLM branch. False-positive heuristic hits waste Ollama calls but do not produce false blocks (the LLM should return `is_injection=false, confidence=high`). Requires tuning the keyword set against real traffic in Phase 3+.
- **Fail-open trades a real risk for reliability.** A novel injection that regex misses AND that Ollama fails to classify (because Ollama is down) reaches the downstream LLM. Regex still catches known-bad, so the exposure is narrow, but it is not zero.
- **Defensive `phi_present=True` on classifier calls is a manual coupling to the BAA gate's flag semantics.** If ADR-0006's coupling contract changes (e.g., the flag is renamed), this call site has to update in lockstep. Mitigated by putting a docstring at the call site pointing back at ADR-0006.

### Neutral / Notable

- **No new field on `CompletionRequest`.** Sentinel decisions are logged (source, pattern, trace_id) but not surfaced on the request object. Rationale: no downstream guardrail reads them today. If the digest agent (build-plan line 32) needs "count injections blocked yesterday," that data comes from the audit log, not from the request tag. Adding a field later is additive — same shape as `phi_present` in ADR-0006.
- **The regex pattern set is a demo-shape stub.** Production injection detection needs a maintained ruleset (LLM Guard, Rebuff, or a commercial signature feed). The `_REGEX_PATTERNS` tuple is the swap-in seam; the `_scan_regex` method's return shape must be preserved.
- **`flag` mode is a valid detection-only rollout.** Same rationale as REDACTION_MODE=off — turn on detection, watch the flag rate for a week, THEN decide to block. Enterprise-friendly rollout path.
- **Suspicion-keyword heuristic runs against the raw user content, not against Unicode-normalized content.** A Unicode-homoglyph attacker can bypass the heuristic (e.g., replacing "i" with a Cyrillic look-alike). This is intentional at Phase 2 — normalization introduces its own attack surface. Post-Phase-3 enhancement: normalize before scanning.

## Alternatives Considered

- **Regex only (handoff option a).** Rejected by user. Fast + deterministic but zero coverage of novel attacks.
- **LLM classifier only (handoff option c).** Rejected by user. High recall but 100–500 ms latency on *every* call and a hard Ollama dependency for the demo path. Same class of over-engineering the ADR-0006 rejection for "use Presidio from day one" ruled out.
- **Always-run LLM classifier (regex + LLM every call, no heuristic).** Rejected. Doubles the "hybrid" latency cost on 90 %+ of traffic that would have passed regex-only. The heuristic exists precisely to skip the LLM on benign content.
- **Sentinel INSIDE the redactor (order: `Redactor(Sentinel(Gate(Router)))`).** Rejected. The redactor would scrub PHI-shaped payloads before the sentinel saw them; an attacker could smuggle instructions inside a "phone number" or "MRN" string and the sentinel would never notice.
- **Classifier gateway = the full outermost stack (`app.state.ai_gateway`).** Rejected. Introduces recursion — the sentinel calls itself. Aborted before consideration.
- **Classifier gateway = raw `TieredAIGateway()` (skip the BAA gate).** Rejected. Violates `CLAUDE.md` rule 3 — the classifier is an LLM call, so it must pass the gate.
- **Classifier call with `phi_present=False`.** Rejected. Silently allows any vendor to receive potentially-PHI-carrying user content, defeating the whole point of the BAA gate. Setting `phi_present=True` defensively is the safe default.
- **Fail-closed on classifier error.** Rejected as default. Single-point-of-failure risk (Ollama down = full outage). May become the correct choice in production; is not the correct choice for a demo.
- **HTTP 403 Forbidden.** Rejected. 403 semantically implies auth/RBAC failure; frontend error-handling maps 403 → "log in again," which is wrong for content policy. 400 is content-correct.
- **HTTP 422 Unprocessable Entity.** Rejected. Closest semantic fit ("we understood but refuse to act") but rarely used in this codebase and less legible in logs than 400. Not worth the training cost for a demo.
- **`SENTINEL_LLM_ENABLED` env flag.** Rejected. Constructor argument (`classifier=None`) already covers the "disable LLM branch" case cleanly. Runtime toggle would be a duplicate control surface.
- **New `injection_flagged: bool` field on `CompletionRequest`.** Rejected. No downstream reader today. Adding it now is speculative abstraction. Add later, additively, if the digest agent or a future L3 auditor needs the coupling — same pattern that produced `phi_present`.

## References

- ADR-0005 (BAA Gate Wraps the Router) — origin of the exception-not-`AIGatewayError` policy pattern and the wrap-the-router shape the sentinel reuses.
- ADR-0006 (L2 Middleware Ordering + `phi_present` Tag) — the redactor-before-gate ordering the sentinel now sits outside of, and the `phi_present` flag the classifier call sets defensively.
- `docs/build-plan.md` line 27 — the sentinel specification this ADR resolves.
- `docs/handoffs/2026-07-07-phase2-tasks-1-2-to-injection-sentinel.md` — the three-option question this ADR closes.
- `CLAUDE.md` non-negotiable rule 3 — "BAA gate is real middleware. Every LLM call passes through. No exceptions." Upheld transitively for the classifier call.
- `app/L2_guardrails/baa_gate.py` — canonical shape for env-driven config, `_enforce` before stream, exception hierarchy.
- `app/L2_guardrails/phi_redactor.py` — canonical shape for `dataclasses.replace` mutation and `_MODE` env resolution.
- Follow-on: digest agent (build-plan line 32) will consume sentinel WARN logs for the "attacks flagged today" digest section. Follow-on: prompt registry (build-plan line 31) will hold the classifier prompt as a versioned entry.
