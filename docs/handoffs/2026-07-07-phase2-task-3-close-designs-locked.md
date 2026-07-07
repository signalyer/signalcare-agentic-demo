# Handoff — Phase 2 task 3 CLOSED · all designs locked → Compliance/Ops implementation

> **Generated:** 2026-07-07 (fifth handoff of the day; end of the injection-sentinel + ADR-0008/0009 design session)
> **From session:** injection sentinel implementation (ADR-0007) + digest UX spec (ADR-0008) + prompt registry storage decision (ADR-0009). Two of the three questions the prior handoff surfaced now resolved via ADRs; the third (detector shape) was answered in-session and shipped as code.
> **To session:** Phase 2 task 4 — build `app/L3_agents/compliance_ops/`, plus the prerequisite `app/L0_observability/prompt_registry/` package. All design blockers cleared.
> **Copy the fenced block below into a fresh Claude Code session to resume.**

---

## Metadata

| Field | Value |
|---|---|
| Repo | `C:\SignalCareAgenticDemo\` (branch `main`, origin at github.com/signalyer/signalcare-agentic-demo) |
| State | Phase 2 tasks 1-3 CLOSED. Runtime stack: `InjectionSentinel(PHIRedactor(BAAGateGuard(TieredAIGateway())), classifier=BAAGateGuard(TieredAIGateway()))`. 96/96 unit tests green offline. All Phase 2 design questions resolved. |
| Head | `4ad327d Docs: ADR-0009 prompt registry — YAML-first Phase 2, Postgres additive Phase 3` (pushed) |
| Blocking action | None. Two minor implementation-time decisions noted below (Fast-tier preprocessing, DIGEST_TZ default). One small doc-hygiene item (rule 6 pointer to ADR-0009). |
| Est. next-session duration | Large — the compliance_ops delivery spans prompt registry + agent + data sources + cron + endpoints + admin UI page + tests. Splitting into 2-3 sessions is realistic (see "Next concrete action" — a-b-c chunking). |
| Commits this session | `7289983` Feat: L2 injection sentinel · `4821251` Docs: reconcile TASKS.md · `a53823d` Docs: ADR-0008 · `4ad327d` Docs: ADR-0009 |

---

## Handoff Prompt (copy from here)

```
# Resume — SignalCare Agentic Demo (Phase 2 task 4 — Compliance/Ops digest agent)

## Where I am

Phase 2 tasks 1-3 CLOSED at commit 4ad327d, pushed to origin/main.
Runtime stack:
    InjectionSentinel(PHIRedactor(BAAGateGuard(TieredAIGateway())),
                      classifier=BAAGateGuard(TieredAIGateway()))
96/96 unit tests green offline. Three ADRs landed this session
(0007 injection sentinel, 0008 digest UX, 0009 prompt registry).
Every Phase 2 design question from the prior handoff is now resolved.

## Decisions already made (don't re-litigate)

- ADR-0001 through ADR-0009 all Accepted. Read in order for the story.
- Injection sentinel (ADR-0007): hybrid regex+LLM detection, gate-wrapped
  classifier avoids recursion, fail-open on classifier error, HTTP 400 on
  block, SENTINEL_MODE=block|flag|off env, SENTINEL_LLM_THRESHOLD env,
  outermost L2 wrap. Every L2 guardrail is an AIGateway decorator --
  do not break this shape for future guardrails.
- Digest UX (ADR-0008): FIXED 5 sections (Attention/Watch/Guardrails/
  Systems/Decisions I need), 300-word body cap, evidence-only synthesis
  (no speculation), guardrail counts are COMPUTED in code and inserted
  into the prompt (LLM never does arithmetic), admin UI page at /digest +
  file at data/digests/YYYY-MM-DD.{md,json}, email deferred to Phase 3.
  Two mockups in the ADR appendix (day-with-signal + quiet-day).
- Prompt registry (ADR-0009): interface first. Phase 2 =
  FileBackedPromptRegistry (YAML at app/L0_observability/prompts/ + JSON
  state snapshot at data/prompt_registry_state.json). Phase 3 =
  PostgresPromptRegistry (additive, same interface). Content-hash
  versioning (sha256[:12]) is substrate-agnostic. CLAUDE.md rule 6
  time-boxed relaxed and restored in Phase 3.
- Tier composition for compliance_ops: Balanced (Sonnet) for synthesis
  is REQUIRED. Fast (Ollama) preprocessing is a design KNOB -- decide
  during implementation whether it earns its keep.
- Renderer is a separate concern from the registry. Registry returns
  PromptDefinition; renderer takes definition + placeholder values and
  produces (system, user) strings with output_schema inlined.

## Key files to load first

- C:\SignalCareAgenticDemo\CLAUDE.md -- project operating rules (rule 6
  is being temporarily relaxed per ADR-0009; the ADR is authoritative)
- C:\SignalCareAgenticDemo\TASKS.md -- Phase 2 tasks 4-9 open; 1-3 have
  commit shas linked
- C:\SignalCareAgenticDemo\docs\adrs\0008-compliance-ops-digest-ux.md --
  the digest spec you are implementing
- C:\SignalCareAgenticDemo\docs\adrs\0009-prompt-registry-yaml-first-postgres-additive.md
  -- the registry spec (schema in section 3, load semantics in 5)
- C:\SignalCareAgenticDemo\docs\build-plan.md lines 20-36 -- Week 2
  goals, DoD (`make demo-digest`), and the /digest/today endpoint spec
- C:\SignalCareAgenticDemo\app\L3_agents\README.md -- every agent's
  contract (registry entry, feature flag, prompt loaded from registry,
  tools via L5, OTEL spans, adversarial-verify for high-stakes)
- C:\SignalCareAgenticDemo\app\L2_guardrails\injection_sentinel.py --
  canonical shape for env-driven config, static _resolve_* methods,
  exception hierarchy. Compliance_ops does NOT wrap AIGateway (not a
  guardrail), but the config-resolution + testability patterns are
  worth copying.
- C:\SignalCareAgenticDemo\app\main.py -- lifespan wiring is where the
  prompt registry singleton lands, the cron trigger installs, and the
  digest endpoints mount

## Outstanding questions (need user input)

1. Fast-tier preprocessing in compliance_ops (ADR-0008 decision 9). The
   Balanced-tier synthesis call is required. A Fast-tier preprocessing
   step (Ollama classifies raw log lines into severity buckets before
   Sonnet synthesizes) is a design knob.
   Recommendation: SKIP for the first pass. The L2 log lines are already
   structured (`decision=allow|deny reason=... trace_id=...`), so regex
   parsing is enough. Add the Fast call later if calibration shows the
   parser missing novel formats.

2. DIGEST_TZ default in .env.example. ADR-0008 decision 8 says the env
   defaults to UTC when unset; Prav's local .env sets America/New_York.
   Options for .env.example: (a) `# DIGEST_TZ=America/New_York` commented
   with a note that unset means UTC, (b) `DIGEST_TZ=UTC` explicit default,
   (c) omit and let the code default kick in.
   Recommendation: (a). Documents the intent + shows Prav's likely value.

3. CLAUDE.md rule 6 inline pointer. Rule 6 says both YAML AND Postgres;
   ADR-0009 relaxes this for Phase 2. A one-line pointer next to rule 6
   ("See ADR-0009 for Phase 2 relaxation") prevents a reviewer from
   misreading rule 6 as violated when they audit the Phase 2 code.
   Recommendation: yes, one-line edit. Ship it in the first compliance_ops
   commit.

## Next concrete action

Implement Phase 2 task 4 -- compliance_ops agent and its prompt-registry
prerequisite. Realistic split across 2-3 sessions:

Session A -- Prompt registry package:
- app/L0_observability/prompts/ directory + first YAML file
  compliance_ops_digest.yaml per ADR-0009 section 3 schema
- app/L0_observability/prompt_registry/ package:
    * types.py -- PromptDefinition dataclass (frozen)
    * registry.py -- PromptRegistry protocol + FileBackedPromptRegistry
    * renderer.py -- PromptRenderer with placeholder validation +
      {output_schema_inline} substitution + PromptRenderError
    * snapshot.py -- read/write data/prompt_registry_state.json +
      drift log (WARN on hash change)
- Wire into main.py lifespan: app.state.prompt_registry singleton
- data/prompt_registry_state.json added to .gitignore
- Tests: tests/unit/test_prompt_registry.py -- load + hash + drift +
  render + missing-placeholder + wrong-tier
- CLAUDE.md rule 6 inline pointer added to that same commit

Session B -- Compliance_ops agent + data sources:
- app/L3_agents/compliance_ops/ package:
    * agent.py -- Balanced-tier synthesis call
    * tools.py -- data source gatherers (psutil host stats, adapter
      health probes, hardening seed loader, L2 guardrail log parse)
    * renderer.py -- JSON -> markdown per ADR-0008 mockups (or reuse
      a shared registry-renderer + agent-specific markdown pass)
    * README.md -- trigger, guardrails, HITL, success metric per L3
      README
- data/seed/hardening_status.json -- seed file per build-plan line 29
- Tests: tests/unit/test_compliance_ops.py -- LLM stubbed, cover the
  JSON-schema render, empty-day mockup match, computed guardrail counts

Session C -- Endpoints, cron, admin UI page:
- main.py: GET /digest/today, GET /digest/{date}, POST /digest/generate
  (env-gated by ALLOW_ONDEMAND_DIGEST=true)
- apscheduler cron trigger in lifespan (hour=6, minute=30, tz=DIGEST_TZ)
- admin_ui/src/pages/Digest.tsx -- reads /digest/today, renders markdown,
  date picker for history
- Live verify with `make demo-digest`
- Update TASKS.md, ADR-0010 if any implementation surprise warrants it

## Working rules in effect

- ~/.claude/CLAUDE.md global standards (session bands, workflow
  classification, handoff protocol, TASKS.md sync)
- C:\SignalCareAgenticDemo\CLAUDE.md project rules -- rule 6 has an
  explicit Phase 2 relaxation via ADR-0009 (both rules are in effect;
  the ADR is the reconciliation)
- Every L2 guardrail is an AIGateway decorator wrapping the next.
  Compliance_ops is an AGENT (L3), not a guardrail -- it does NOT
  implement AIGateway. It CONSUMES the AIGateway via app.state.
- Persist future handoffs to docs/handoffs/YYYY-MM-DD-*.md (never
  inline-only)
- Every architectural decision needs a written ADR. ADR-0010+ likely
  captures some aspect of the compliance_ops or prompt-registry impl
  that surprises us during build.
- Prefer additive over invasive -- new files, new decorators, new fields
  with defaults. No invasive refactors of L2 or L6.
- Run tests via ./app/.venv/Scripts/pytest.exe tests/unit/ from repo
  root (NOT `uv run pytest` -- the venv is in app/, uv from repo root
  does not find it)
- No load_dotenv wiring; uvicorn --env-file ..\.env is the pattern
  (migration to pydantic-settings deferred to Phase 3 kickoff)

## Persona

Direct and critical. Push back when something is wrong. Working code
beats clever abstractions. The audience is enterprise architects who
read the ADR sequence 0001-0009 alongside the code. Every ADR either
references its predecessors or is referenced by successors -- keep the
chain intact when 0010+ lands.
```

---

## What this handoff replaces

Predecessor: `docs/handoffs/2026-07-07-phase2-tasks-1-2-to-injection-sentinel.md` (Phase 2 tasks 1+2 CLOSED, injection sentinel staged with three open design questions).

That handoff was consumed by this session, which:

- Answered its **question 1** in-session ("hybrid detector, HTTP 400"), then delivered ADR-0007 + the injection sentinel implementation + 46 new unit tests + wiring + env vars. Phase 2 task 3 CLOSED.
- Answered its **question 2** ("what does the digest look like") as ADR-0008 — a full UX spec with two rendered mockups.
- Answered its **question 3** ("prompt registry storage given Postgres is deferred") as ADR-0009 — interface-first with a Phase 2 FileBackedPromptRegistry and a Phase 3 PostgresPromptRegistry, plus a documented time-boxed relaxation of `CLAUDE.md` rule 6.

## What the next handoff should cover

End of the compliance_ops build (or its first chunk, if split across sessions per the a-b-c chunking above). At a minimum:

- Prompt registry package landed and tested (the piece the agent depends on).
- `compliance_ops_digest.yaml` written per ADR-0009 §3 schema.
- Live-verify `make demo-digest` produces a real-looking founder brief.

If the build surfaces any surprise, spin an ADR-0010 (or higher) for it. Continue the chain.
