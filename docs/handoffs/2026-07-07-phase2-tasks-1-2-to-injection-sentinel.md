# Handoff — Phase 2 tasks 1+2 CLOSED → Injection Sentinel + Compliance/Ops kickoff

> **Generated:** 2026-07-07 (fourth handoff of the day; end of the Phase 2 opening two-task session)
> **From session:** ADR-0005 wrap-the-router BAA gate, ADR-0006 redactor-before-gate + phi_present coupling. Two L2 guardrails live, 50/50 unit tests green.
> **To session:** Phase 2 task 3 — L2 injection sentinel; then task 4 — Compliance/Ops (Founder Mode) digest agent; then prompt registry + admin UI digest page (all in the same phase, all still Week 2 scope).
> **Copy the fenced block below into a fresh Claude Code session to resume.**

---

## Metadata

| Field | Value |
|---|---|
| Repo | `C:\SignalCareAgenticDemo\` (branch `main`, origin at github.com/signalyer/signalcare-agentic-demo) |
| State | Phase 2 tasks 1 (BAA gate) + 2 (PHI redactor) CLOSED; L2 stack `PHIRedactor(BAAGateGuard(TieredAIGateway))` live and unit-tested |
| Head | `4117757 Docs: reconcile TASKS.md after L2 PHI redactor + BAA retrofit 7d104ba` (assuming pushed by session-close) |
| Blocking action | None. Ready to start Phase 2 task 3 (injection sentinel). Two open design points pending (injection detector shape, digest UX). |
| Est. next-session duration | ~30 hours (rest of Week 2, solo full-time) |

---

## Handoff Prompt (copy from here)

```
# Resume — SignalCare Agentic Demo (Phase 2 tasks 3-8 — injection sentinel + digest agent + prompt registry)

## Where I am

Phase 2 tasks 1 and 2 CLOSED at commit 4117757. Five commits on branch main
at C:\SignalCareAgenticDemo, pushed to origin.

Two L2 guardrails live and unit-tested:
- BAAGateGuard — wraps TieredAIGateway; blocks unapproved vendors when
  req.phi_present is True. Denials -> BAAGateError -> HTTP 451. See ADR-0005.
- PHIRedactor — outermost wrapper; regex-based T1-T4 detection; sets
  phi_present and phi_tier on the outgoing CompletionRequest via
  dataclasses.replace. REDACTION_MODE env: strict|standard|off. See ADR-0006.

Runtime stack in main.py lifespan:
    router = TieredAIGateway()               # L6
    gated  = BAAGateGuard(router)            # L2 read
    stack  = PHIRedactor(gated)              # L2 write. Outermost. Runs first.
    app.state.ai_gateway = stack

Tests: 50/50 unit passing offline. No integration tests were added this
session -- the runtime path is exercised via unit tests with fake routers;
live verification of the redactor+gate through /agents/echo is still open
(low priority, since the guard is empirically clean on the demo path where
both vendors are approved).

CompletionRequest shape now includes phi_present: bool = False and
phi_tier: str | None. Defaults preserve prior caller behavior.

## Decisions already made (don't re-litigate)

- ADR-0001: Python 3.12+ (running 3.14.3) + FastAPI + Pydantic v2 + asyncio
- ADR-0002: Cloud-agnostic via adapter pattern with real local implementations
- ADR-0003: Docker-compose stack deferred to Phase 3 (native Ollama covers)
- ADR-0004: Hosted tier uses direct Anthropic SDK, NOT OpenRouter
- ADR-0005: BAA gate WRAPS THE ROUTER, not individual adapters. BAAGateError
  inherits from Exception, NOT AIGatewayError. Denials map to HTTP 451.
- ADR-0006: Redactor is OUTSIDE gate in the middleware wrap order. The
  phi_present tag is the coupling contract between them and lives inline
  on CompletionRequest (rejected: sidecar RequestMetadata, gate-scans-itself,
  gate-before-redactor, third orchestrator, FastAPI-level middleware).
- REDACTION_MODE=strict as the demo default (redact T1+T2 to tokens). The
  `off` mode exists specifically for observability-first rollouts elsewhere.
- Regex-based PHI detection now; Presidio is the future swap-in point noted
  in phi_redactor._scan_content docstring. Do NOT add Presidio in Phase 2.
- Every L2 guardrail is an AIGateway decorator. This shape MUST be preserved
  for the next guardrail (injection sentinel) so the runtime composition
  stays `Sentinel(Redactor(Gate(Router)))` — no ad-hoc APIs.
- Env loading: uvicorn `--env-file ..\.env`. NO load_dotenv is wired.
  Migration to pydantic-settings Settings deferred to Phase 3 kickoff.

## Key files to load first

- C:\SignalCareAgenticDemo\CLAUDE.md — project operating rules
- C:\SignalCareAgenticDemo\TASKS.md — Phase 2 items 3-9 open; items 1-2 have
  commit shas linked
- C:\SignalCareAgenticDemo\ARCHITECTURE.md — L2 subgraph shows the peer
  guardrails; runtime order set by ADR-0006
- C:\SignalCareAgenticDemo\docs\build-plan.md — Week 2 deliverables; line 27
  is the injection sentinel spec, line 30 is the prompt-registry spec
- C:\SignalCareAgenticDemo\docs\adrs\0005-*.md and 0006-*.md — L2 pattern
- C:\SignalCareAgenticDemo\app\L2_guardrails\baa_gate.py — canonical wrap
  shape; injection sentinel should mirror the structure
- C:\SignalCareAgenticDemo\app\L2_guardrails\phi_redactor.py — mutation
  pattern via dataclasses.replace; regex-first with Presidio swap-in note
- C:\SignalCareAgenticDemo\app\main.py — lifespan wiring; the new sentinel
  wraps PHIRedactor at the outermost position
- C:\SignalCareAgenticDemo\tests\unit\test_baa_gate.py + test_phi_redactor.py
  — proven test patterns to copy for test_injection_sentinel.py

## Outstanding questions (need user input)

1. Injection sentinel detector shape — options:
   (a) regex-based, small set of known injection patterns (jailbreaks like
       "ignore previous instructions", "you are now DAN", markdown-token
       smuggling, base64 payloads). Fast, offline, no API call.
   (b) LLM-based classifier using the Fast tier (Ollama) — sends the user
       message to a classifier prompt and returns risk score.
   (c) hybrid — regex first as a cheap pre-filter, LLM fallback for medium
       risk.
   Recommendation: START (a) for Phase 2, add (b) as a future enhancement.
   Rationale matches the phi_redactor decision: pragmatic detection first,
   ML swap-in noted. Sentinel probably has a `SENTINEL_MODE=block|flag|off`
   env analogous to REDACTION_MODE.
2. Digest UX design — the Compliance/Ops (Founder Mode) agent produces a
   daily 06:30 digest per build-plan line 32. WHAT does the digest LOOK like
   before we write the agent? Sections? Length? Tone? Distribution channel
   (email, admin-UI page, both)? Design a mockup or written spec BEFORE
   writing the LLM prompt. Do NOT start compliance_ops/ without this.
3. Prompt registry storage — build-plan line 31 says YAML source of truth +
   Postgres runtime table synced on startup. But Postgres isn't running yet
   (deferred with docker stack per ADR-0003). Interim options: (i) YAML-only
   for Phase 2, defer Postgres to Phase 3 when compute adapter lands; (ii)
   SQLite as a stand-in until the compose stack comes up; (iii) hand-rolled
   in-memory dict seeded from YAML. Recommendation: (i). Simplest, matches
   ADR-0003's spirit; Phase 3 adds the Postgres sync as part of the compute
   adapter delivery.

## Next concrete action

Phase 2 task 3 per TASKS.md is `app/L2_guardrails/injection_sentinel.py`.
Same middleware shape as BAAGateGuard and PHIRedactor. Answer question 1
before writing; my recommendation is (a) regex-based, ~10 patterns to
start, `SENTINEL_MODE` env with block/flag/off, and a typed
`InjectionSentinelError` -> HTTP 400 (or 403; pick with the user).

Then move on per TASKS.md Phase 2 checklist:
- L3 agents / compliance_ops (needs digest UX from question 2)
- Data sources: docker stats (deferred, use fake JSON), Postgres audit
  table (deferred, use fake JSON), hardening_status.json seed
- Prompt registry (question 3)
- Cron job for daily digest (apscheduler per build-plan)
- Simple /digest/today endpoint + admin UI page
- Test: end-to-end from cron trigger -> LLM -> digest text produced

## Working rules in effect

- ~/.claude/CLAUDE.md global standards (session bands, workflow classification,
  handoff protocol)
- C:\SignalCareAgenticDemo\CLAUDE.md project rules — no cloud SDK outside
  L6_adapters; every request has trace_id; synthetic data only; BAA gate is
  real middleware not a stub; adversarial persona; every L2 guardrail is an
  AIGateway decorator wrapping the next.
- Persist future handoffs to docs/handoffs/YYYY-MM-DD-*.md (never inline-only)
- Every architectural decision needs a written ADR (0007 will likely be the
  injection sentinel design; 0008+ for digest UX, prompt registry)
- Prefer additive over invasive; the phi_present tag on CompletionRequest was
  the last additive extension. Any further extension should be similarly
  minimal.
- Run tests via ./app/.venv/Scripts/pytest.exe tests/unit/ from repo root
  (NOT `uv run pytest` — the venv is in app/, uv from repo root doesn't
  find it)

## Persona

Direct and critical. Push back when something is wrong. Working code beats
clever abstractions. The audience is enterprise architects — they will
read the code AND the ADR sequence, which now stands at 0001-0006 with
each ADR answering questions raised by prior ones.
```

---

## What this handoff replaces

Predecessor: `docs/handoffs/2026-07-07-phase1-close-to-phase2.md` (Phase 1 CLOSED, Phase 2 kickoff ready). That handoff staged the opening move (baa_gate.py) and was consumed by the session that produced ADR-0005, ADR-0006, the PHI redactor, and the BAA gate conditional retrofit.

## What the next handoff should cover

End of Week 2 / Phase 2 CLOSE: injection sentinel operational, Compliance/Ops (Founder Mode) digest agent running on cron, first version of the prompt registry (YAML source of truth — Postgres sync deferred to Phase 3), admin UI digest page live. Author at `docs/handoffs/YYYY-MM-DD-phase2-close-to-phase3.md`. Include the digest UX decision as an ADR (0008 or thereabouts).
