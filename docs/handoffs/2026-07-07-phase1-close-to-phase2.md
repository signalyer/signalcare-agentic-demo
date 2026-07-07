# Handoff — Phase 1 CLOSED → Phase 2 (Week 2) Kickoff

> **Generated:** 2026-07-07 (third handoff of the day; end of the Phase 1 live-verify session)
> **From session:** ADR-0003 (docker deferral), ADR-0004 (Anthropic direct SDK), all three tiers live-verified, 13+3 tests green
> **To session:** Phase 2 kickoff — L2 guardrails + Compliance/Ops (Founder Mode) agent
> **Copy the fenced block below into a fresh Claude Code session to resume.**

---

## Metadata

| Field | Value |
|---|---|
| Repo | `C:\SignalCareAgenticDemo\` (branch `main`, no remote yet) |
| State | Phase 1 CLOSED; all Week 1 code deliverables live-verified with real providers |
| Head | `aa0b771 Feat: pivot hosted tier to direct Anthropic SDK; Phase 1 CLOSED` |
| Blocking action | None. Ready to start Phase 2. Two open design points pending (env-loading, git remote) |
| Est. next-session duration | ~40 hours (Week 2, solo full-time) |

---

## Handoff Prompt (copy from here)

```
# Resume — SignalCare Agentic Demo (Phase 2 kickoff)

## Where I am

Phase 1 CLOSED at commit aa0b771. Four commits on branch main at
C:\SignalCareAgenticDemo, no remote. The L6 AI Gateway adapter shipped and was
live-verified against three tiers end-to-end this session:

- Fast: Ollama llama3.2:3b via http://localhost:11434 (warm 601 ms)
- Balanced: Anthropic claude-sonnet-4-6 direct SDK (1091 ms)
- Reasoning: Anthropic claude-opus-4-7 direct SDK (1603 ms)

Tests: 13 unit + 3 integration, all green. The load-bearing test
test_same_interface_serves_two_providers passes -- same CompletionRequest shape,
two genuinely different provider SDKs (Ollama REST + Anthropic SDK), ADR-0002
proof-point empirically validated.

Runtime state: Ollama installed natively via winget, running as a Windows
service. Python 3.14.3 + uv + populated app/.venv (uv sync + uv sync --extra dev).
Docker NOT installed and deferred to Phase 3 per ADR-0003.

## Decisions already made (don't re-litigate)

- ADR-0001: Python 3.12 + FastAPI + Pydantic v2 + asyncio for the demo backend
- ADR-0002: Cloud-agnostic via adapter pattern with real local implementations
- ADR-0003: Docker-compose stack deferred to Phase 3 (native Ollama covers Week 1)
- ADR-0004: Hosted tier uses direct Anthropic SDK, NOT OpenRouter (rationale in
  the ADR includes the actual 402 no-credits transcript that triggered the pivot)
- Env loading is via `uvicorn main:app --env-file ..\.env` (Path A). NO
  load_dotenv is wired into main.py. Confirm A stays or migrate to pydantic-
  settings Settings (Path B) BEFORE Phase 3 credentials wiring lands.
- Adapter interface stays `complete` + `stream` + `supports_tier`. Tool-calling
  is deferred until the first tool-using agent needs it (Compliance/Ops in this
  phase may -- see below).
- `_build_kwargs` sentinel-pattern for Anthropic temperature is the shape for
  handling future per-provider quirks -- keep provider chaos inside adapter code
  and out of router / agent code.

## Key files to load first

- C:\SignalCareAgenticDemo\CLAUDE.md -- project operating rules
- C:\SignalCareAgenticDemo\TASKS.md -- Phase 2 checklist starts at "Phase 2 --
  Week 2" section; Phase 1 all closed with commit sha references
- C:\SignalCareAgenticDemo\ARCHITECTURE.md -- layer definitions
- C:\SignalCareAgenticDemo\docs\adrs\ (0001-0004)
- C:\SignalCareAgenticDemo\app\L6_adapters\ai_gateway\ (base, local, anthropic_gateway, router)
- C:\SignalCareAgenticDemo\app\main.py -- lifespan wiring pattern for Phase 2
  guardrail middleware
- C:\SignalCareAgenticDemo\pytest.ini + tests/conftest.py
- C:\SignalCareAgenticDemo\docs\handoffs\2026-07-07-week1-core-to-live-verify.md (predecessor)

## Outstanding questions (need user input)

1. Env-loading path COMMIT: keep Path A (`--env-file`) documented in README, or
   migrate to Path B (pydantic-settings Settings) now. Phase 3 has NATS + Vault +
   Postgres creds -- Path B is cleaner there, but adding it now is scope creep for
   Phase 2. My rec: stay A, revisit at Phase 3 kickoff.
2. Git remote: `origin` not set. If pushing to github.com/signalyer/<repo>, need
   to `git remote add origin <url>` + `git push -u origin main`. Confirm repo name
   first (SignalCareAgenticDemo? signalcare-agentic-demo? something else?).
3. Compliance/Ops (Founder Mode digest) data sources: real docker stats are gone
   (docker deferred), Postgres audit table doesn't exist yet (Phase 3), so the
   digest agent needs a fake `hardening_status.json` + fake docker-stats file
   for Week 2. Design the digest UX (what does the daily 06:30 digest LOOK like?)
   before writing the agent.

## Next concrete action

Phase 2 first task per TASKS.md is `app/L2_guardrails/baa_gate.py` -- the "no
LLM call without BAA verification" middleware. Every subsequent Phase 2 delivery
runs through it, so getting it right early prevents rework.

Design pattern (from architecture doc):
1. Middleware inspects every outbound LLM call (intercepts adapter.complete/stream).
2. Reads the target provider from the CompletionRequest/adapter metadata.
3. Checks against APPROVED_PHI_VENDORS from env.
4. If REQUIRE_BAA=true and vendor is not approved, raise a typed error surfaced
   as HTTP 451 (Unavailable For Legal Reasons) at the API boundary.
5. Every request has a trace_id; log the gate decision (allow/deny) with trace_id
   so the audit log is queryable.

Integration point: wrap TieredAIGateway (or the individual concrete adapters) in
a BAAGateGuard that satisfies the same AIGateway interface. This preserves the
abstraction from ADR-0002 while making the guardrail middleware-shaped.

Then move on per TASKS.md Phase 2 checklist: phi_redactor.py, injection_sentinel.py,
compliance_ops agent, YAML+Postgres prompt registry, admin UI digest page.

## Working rules in effect

- ~/.claude/CLAUDE.md global standards
- C:\SignalCareAgenticDemo\CLAUDE.md project rules (no cloud SDK outside
  L6_adapters, every request has trace_id, synthetic data only, BAA gate is real
  middleware not a stub, adversarial persona)
- Persist future handoffs to docs/handoffs/YYYY-MM-DD-*.md (never inline-only)
- Every architectural decision needs a written ADR
- Prefer additive over invasive

## Persona

Direct and critical. Push back when something is wrong. Working code beats
clever abstractions. The audience is enterprise architects -- they will read
the code AND the ADR sequence, which now stands at 0001-0004 with each ADR
answering questions raised by prior ones.
```

---

## What this handoff replaces

Predecessor: `docs/handoffs/2026-07-07-week1-core-to-live-verify.md` (Phase 1 core committed → live verify pending). That handoff was consumed and superseded by the live-verification session that produced ADR-0004 and closed Phase 1.

## What the next handoff should cover

End of Week 2 / Phase 2 close: BAA gate middleware working, PHI redactor + injection sentinel operational, Compliance/Ops (Founder Mode) digest agent running on cron, first version of the prompt registry (YAML source of truth + Postgres runtime table) live. Author at `docs/handoffs/YYYY-MM-DD-phase2-close-to-phase3.md`.
