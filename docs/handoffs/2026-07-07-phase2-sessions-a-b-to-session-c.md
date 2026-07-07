# Handoff — Phase 2 task 4 sessions A+B landed → Session C (endpoints + cron + admin UI + Phase 2 CLOSE)

> **Generated:** 2026-07-07 (sixth handoff of the day; end of the compliance_ops package build)
> **From session:** Session A (L0 prompt_registry + first canonical YAML) + Session B (L3 compliance_ops agent, tools, renderer, hardening seed, rotating log wiring). Both commits pushed. Prior handoff's 3 open decisions all resolved during this session — no design blockers remain for Session C.
> **To session:** Phase 2 task 4 Session C — endpoints + cron + admin UI Digest page + `make demo-digest` live verify + Phase 2 CLOSE handoff.
> **Copy the fenced block below into a fresh Claude Code session to resume.**

---

## Metadata

| Field | Value |
|---|---|
| Repo | `C:\SignalCareAgenticDemo\` (branch `main`, origin at github.com/signalyer/signalcare-agentic-demo) |
| State | Phase 2 tasks 1-3 CLOSED, task 4 sessions A+B CLOSED. Compliance_ops agent ships end-to-end at `app/L3_agents/compliance_ops/`. Runtime stack unchanged (L2 stack from Session B of Phase 2 task 3 still valid). 151/151 unit tests green offline. |
| Head | `8319c1a Feat: L3 compliance_ops agent + Founder Mode digest (ADR-0008)` (pushed) |
| Prior commit | `a69a267 Feat: L0 prompt_registry + first canonical YAML (ADR-0008/0009)` (pushed) |
| Blocking action | None. All design decisions from prior handoff resolved (rule-6 pointer landed in Session A; Fast-tier preprocessing skipped per recommendation; `DIGEST_TZ` documented in `.env.example` in this handoff commit). |
| Est. next-session duration | Medium. Endpoints + cron + admin UI + live verify. Realistic split into one session unless the admin UI grows scope. |
| Commits this session | `a69a267` (Session A) · `8319c1a` (Session B) |

---

## Handoff Prompt (copy from here)

```
# Resume — SignalCare Agentic Demo (Phase 2 task 4 Session C — endpoints + cron + admin UI + Phase 2 CLOSE)

## Where I am

Phase 2 tasks 1-3 CLOSED. Task 4 Session A + B CLOSED and pushed.
Runtime stack (from task 3, unchanged):
    InjectionSentinel(PHIRedactor(BAAGateGuard(TieredAIGateway())),
                      classifier=BAAGateGuard(TieredAIGateway()))
Compliance_ops end-to-end at app/L3_agents/compliance_ops/:
    agent.py, tools.py, renderer.py, README.md, __init__.py.
Prompt registry at app/L0_observability/prompt_registry/ + first
canonical YAML at app/L0_observability/prompts/compliance_ops_digest.yaml.
Rotating log at data/logs/signalcare.log wired in main.py lifespan.
Hardening seed at data/seed/hardening_status.json (8 controls).
151/151 unit tests green offline (55 new across A+B).

Head: 8319c1a. Nothing outstanding on disk.

## Decisions already made (don't re-litigate)

- ADR-0001 through ADR-0009 all Accepted.
- Prompt registry (ADR-0009): FileBackedPromptRegistry loaded once in
  main.py lifespan, exposed as app.state.prompt_registry. PromptRegistry
  is a Protocol; Phase 3 PostgresPromptRegistry is a swap-in-place
  additive. Rule-6 pointer to ADR-0009 landed in CLAUDE.md.
- Renderer split from registry: PromptRenderer auto-inlines
  {output_schema_inline} from definition.output_schema. Callers must
  NOT supply that placeholder.
- ComplianceOpsAgent CONSUMES app.state.ai_gateway; does NOT wrap it.
  L3 agents are consumers; L2 guardrails are the only AIGateway
  decorators.
- Renderer (compliance_ops/renderer.py) is deterministic. Two ADR-0008
  Appendix mockups are byte-exact regression tests; don't drift the
  format without amending the ADR.
- Guardrails counts and systems states come from tool output, NOT the
  LLM. Agent overwrites guardrails (WARN + DigestResult flag on divergence)
  and replaces systems entirely with computed truth. LLMs miscount.
- Sections cap at 3 with WARN + DigestResult.caps_triggered flag.
- Log file at data/logs/signalcare.log (rotating 10MB * 3) is the source
  the guardrail-count tool greps. Missing file = zeros, first-run OK.
- Fast-tier Ollama preprocessing NOT implemented for compliance_ops.
  Balanced-only synthesis per ADR-0008 §9 design knob; add later if
  calibration shows regex parser missing novel log formats.
- Adapter probes accept an injected httpx.AsyncClient (tests use
  MockTransport). Production leaves it None; tools layer builds a
  short-lived client per pass.
- data/digests/ and data/logs/ are gitignored (runtime artifacts).
  data/prompt_registry_state.json is gitignored (drift-detection sidecar).
- DIGEST_TZ (default UTC) and ALLOW_ONDEMAND_DIGEST (default false)
  documented as commented lines in .env.example.

## Key files to load first

- C:\SignalCareAgenticDemo\CLAUDE.md — project rules (rule 6 has the
  ADR-0009 pointer).
- C:\SignalCareAgenticDemo\TASKS.md — Phase 2 task 4 A+B closed; cron +
  admin UI + live verify open.
- C:\SignalCareAgenticDemo\docs\adrs\0008-compliance-ops-digest-ux.md
  §2 (distribution surfaces) + §8 (trigger + persistence).
- C:\SignalCareAgenticDemo\docs\build-plan.md lines 20-36 — Week 2 DoD
  (`make demo-digest`, `/digest/today` endpoint).
- C:\SignalCareAgenticDemo\app\main.py — lifespan is where the cron
  trigger installs and the digest endpoints mount. app.state.ai_gateway,
  app.state.prompt_registry both already live here; agent construction +
  scheduler start belong at the end of the startup block.
- C:\SignalCareAgenticDemo\app\L3_agents\compliance_ops\agent.py —
  ComplianceOpsAgent constructor shape (dependency injection, http_client
  seam for tests) is what the endpoint + cron code will instantiate.
- C:\SignalCareAgenticDemo\app\L3_agents\compliance_ops\README.md —
  purpose, trigger, guardrails posture; describes what Session C must
  deliver (endpoints, cron, no HITL gate).
- C:\SignalCareAgenticDemo\admin_ui\ — Next.js 15 shell already scaffolded
  (Phase 0). Existing pages give the React + Tailwind + shadcn conventions.
- C:\SignalCareAgenticDemo\Makefile — add the `demo-digest` target next
  to whatever exists.

## Outstanding questions (need user input)

1. Scheduler library. apscheduler is the ADR-0008 named choice, adds
   ~2 deps. Alternatives: (a) asyncio.create_task with a sleep-until-time
   loop (zero deps), (b) system cron / Windows Task Scheduler calling the
   POST endpoint (out of process). Recommendation: apscheduler with
   AsyncIOScheduler backend — same event loop as FastAPI, timezone
   support built in via zoneinfo, and one less thing to reason about
   than DIY.

2. Admin UI markdown rendering. The Digest.tsx page reads
   /digest/today (JSON) and needs to render the markdown. Options:
   (a) call GET on the .md file too and render with react-markdown,
   (b) render markdown client-side from the JSON via the same
   renderer.py logic (duplicated in TS), (c) server returns pre-rendered
   HTML. Recommendation: (a) — smallest split, react-markdown is a
   well-worn dep, and the .md file already exists on disk.

3. POST /digest/generate — how gated. ADR-0008 §2 says env-gated by
   ALLOW_ONDEMAND_DIGEST=true. Should there be additional auth?
   Recommendation: for the demo, no. The env gate is enough because
   the endpoint is only exposed on localhost via CORS during
   development. Add proper auth as part of Phase 5's identity work.

4. `make demo-digest` live verify — call the real Anthropic model?
   Recommendation: yes. The proof-point is that the whole L1→L2→L6
   stack runs end-to-end and produces a real founder brief. If the
   Anthropic call is stubbed, the demo is a lie. Cost per run is
   pennies at Balanced tier / 1200 max_tokens.

## Next concrete action

Session C — Phase 2 CLOSE. Realistic scope:

1. Add apscheduler + react-markdown deps.
2. main.py lifespan additions (in this order):
   - Construct ComplianceOpsAgent with the app.state gateway + prompt
     registry + PromptRenderer(). Paths anchored to Path(__file__).
   - AsyncIOScheduler with cron trigger (hour=6, minute=30, tz from
     DIGEST_TZ env; default UTC). scheduler.add_job(agent.run_daily);
     scheduler.start() at startup, scheduler.shutdown() at shutdown.
   - app.state.digest_agent = agent so endpoints can access it.
3. main.py endpoints:
   - GET /digest/today → reads today's YYYY-MM-DD.json from disk;
     404 with {"error": "no digest generated yet today"} if missing.
   - GET /digest/{YYYY-MM-DD} → reads specific date's .json.
   - POST /digest/generate → gated by ALLOW_ONDEMAND_DIGEST env.
     Calls agent.run_daily() and returns the DigestResult as JSON.
4. admin_ui/src/pages/Digest.tsx or app/(digest)/page.tsx:
   - Fetches /digest/today for JSON metadata (date, generated_at)
   - Fetches the .md via a new GET /digest/today/markdown endpoint
     (or a shared JSON→markdown TS module — pick based on question 2)
   - Date picker for history (queries /digest/{date}).
5. Makefile: `demo-digest` target that curls the POST endpoint (or
   invokes `python -m ...` for direct call) and prints where the
   files landed.
6. Tests: expand tests/unit/test_compliance_ops.py OR add
   tests/integration/test_digest_flow.py — cover the endpoints with
   FastAPI TestClient + agent stubbed. Live-verify path is exercised
   manually via make demo-digest.
7. TASKS.md — flip cron + admin UI + full-flow test rows; declare
   Phase 2 CLOSED with commit sha. Add a Phase 3 preface note.
8. Handoff for Phase 3 kickoff — next agent (probably
   document_extraction) or Postgres arrival.

## Working rules in effect

- ~/.claude/CLAUDE.md global standards (session bands, workflow
  classification, handoff protocol, TASKS.md sync).
- C:\SignalCareAgenticDemo\CLAUDE.md project rules — rule 6 has the
  ADR-0009 pointer. Rule 3 (BAA gate) applies to the digest LLM call —
  phi_present=False (non-PHI agent), which the agent already sets
  implicitly via the AIGateway request.
- Every architectural decision needs a written ADR. If the scheduler
  choice, /digest endpoint shape, or admin UI approach surprises us
  during build, spin ADR-0010 (or higher). Continue the chain.
- Prefer additive over invasive — Session B added ~1867 lines; Session
  C should be closer to ~500-800. No refactors of A/B code without a
  concrete reason.
- Persist future handoffs to docs/handoffs/YYYY-MM-DD-*.md.
- Run tests via ./app/.venv/Scripts/pytest.exe from repo root with
  --basetemp=.pytest-tmp (system-temp permissions issue; .pytest-tmp
  is gitignored).
- No load_dotenv; uvicorn --env-file ..\.env is the pattern.

## Persona

Direct and critical. Push back when something is wrong. Working code
beats clever abstractions. The audience is enterprise architects who
read the ADR sequence 0001-0009 alongside the code. Session C closes
Phase 2 — the shape must be defensible in an architect review, not just
"it works".
```

---

## What this handoff replaces

Predecessor: [`docs/handoffs/2026-07-07-phase2-task-3-close-designs-locked.md`](2026-07-07-phase2-task-3-close-designs-locked.md) (Phase 2 task 3 CLOSED, all Phase 2 design blockers resolved via ADR-0007/0008/0009, ready to build compliance_ops in Sessions A+B+C).

That handoff was consumed by this session, which delivered:

- **Session A** (commit `a69a267`): L0 `prompt_registry` package per ADR-0009 (types + registry protocol + FileBackedPromptRegistry + renderer + snapshot), first canonical YAML `compliance_ops_digest.yaml` per ADR-0008 §5, main.py lifespan wiring, CLAUDE.md rule 6 pointer, 28 new unit tests. Answers prior handoff decision 3 ("CLAUDE.md rule 6 inline pointer") in place.
- **Session B** (commit `8319c1a`): L3 `compliance_ops` package (agent + tools + renderer + README + `__init__.py`), rotating log at `data/logs/signalcare.log`, hardening seed at `data/seed/hardening_status.json`, psutil dep, 27 new unit tests (including byte-exact matches of ADR-0008 Appendix A + B mockups). Skips prior handoff decision 1 (Fast-tier preprocessing) per recommendation; will revisit only if calibration shows the regex log parser missing novel formats.
- **This handoff commit**: adds `DIGEST_TZ` and `ALLOW_ONDEMAND_DIGEST` as commented lines in `.env.example` (prior handoff decision 2), and this file. So Session C's implementer never has to reconstruct the env seam.

## What the next handoff should cover

**Phase 2 CLOSE.** End of Session C. At a minimum:

- Cron trigger fires at 06:30 (verified by a fast-forward test or a manual sleep-until-time run).
- `/digest/today`, `/digest/{date}`, `POST /digest/generate` all mounted and 200-tested.
- Admin UI `/digest` page renders the latest markdown, has a date picker for history.
- `make demo-digest` produces a real founder brief from a live Anthropic Balanced-tier call.
- TASKS.md Phase 2 rows all `[x]` and the "Phase 2 CLOSED at commit XXXXXXX" note added.
- Handoff points at whatever Phase 3 kicks off with — most likely `L6_adapters/relational/` (Postgres) since that unlocks `PostgresPromptRegistry`, the L2B evidence fabric, and rule 6's letter-restoration.

If Session C surfaces any surprise (apscheduler edge case, admin UI framework version drift, cron TZ handling under Windows), spin an ADR-0010+ for it before landing the fix. The chain must stay intact.
