# Handoff — Phase 2 task 4 Session C-backend landed → C-frontend (admin UI scaffold + `/digest` page + Phase 2 CLOSE)

> **Generated:** 2026-07-07 (seventh handoff of the day; Session C split into C-backend / C-frontend)
> **From session:** Session C-backend — apscheduler cron trigger, 5 `/digest/*` endpoints, Makefile `demo-digest` target, 46 endpoint contract tests. Phase 2 CLOSE is one session away.
> **To session:** C-frontend — ADR-0010 (Next.js App Router + Tailwind + shadcn stack decisions), full `admin_ui/` scaffold, `/digest` page with markdown rendering + date picker, live verify against a `make demo-digest` run, Phase 2 CLOSE handoff.
> **Copy the fenced block below into a fresh Claude Code session to resume.**

---

## Why this split exists (context for the reader)

The prior handoff (`2026-07-07-phase2-sessions-a-b-to-session-c.md`, line 98-99) stated: *"admin_ui/ — Next.js 15 shell already scaffolded (Phase 0). Existing pages give the React + Tailwind + shadcn conventions."*

**That was wrong.** Verified at Session C start: `admin_ui/` contained only empty directories — 0 files. No `package.json`, no `next.config.js`, no components. Building a `/digest` page on top of that non-existent shell would have required scaffolding Next.js 15 + Tailwind + shadcn from scratch (~1500 lines of config + provider tree + primitives) alongside the backend cron + endpoints + tests. That ballooned Session C outside its Refactoring-band Normal envelope AND baked an unreviewed architectural decision (App Router vs Pages Router, dark-mode strategy, shadcn version pin) into a rushed shot.

**Decision:** split Session C into C-backend (this handoff's origin) and C-frontend (this handoff's target). Backend delivered independently — the `/digest` endpoints exist NOW and can be curled today. The frontend gets its own session with its own ADR-0010 to make the stack decisions properly.

The precedence rule: **Phase 3 does NOT start until C-frontend closes Phase 2.** No leaking of scope.

---

## Metadata

| Field | Value |
|---|---|
| Repo | `C:\SignalCareAgenticDemo\` (branch `main`, origin at github.com/signalyer/signalcare-agentic-demo) |
| State | Phase 2 tasks 1-3 CLOSED, task 4 Sessions A+B CLOSED, Session C-backend CLOSED. Compliance_ops end-to-end with cron trigger + 5 endpoints wired. 198/198 offline tests green (46 new in `test_digest_flow.py`). **Backend can be curled RIGHT NOW; UI page is what remains for Phase 2 close.** |
| Head | *(uncommitted at handoff time — see "Commits this session" below; commit before starting C-frontend)* |
| Prior commit | `8319c1a Feat: L3 compliance_ops agent + Founder Mode digest (ADR-0008)` (Session B) |
| Blocking action | Commit Session C-backend before starting C-frontend. Suggested subject: `Feat: Phase 2 backend close — compliance_ops cron + /digest endpoints (ADR-0008)`. |
| Est. next-session duration | Medium-large. ADR-0010 (~200 lines) + Next.js scaffold (~800 lines of config + layout + providers) + `/digest` page (~400 lines) + live verify. Sits in the Refactoring band's Normal envelope only because backend already exists. |
| Files touched this session | `app/pyproject.toml`, `app/main.py`, `Makefile`, `TASKS.md`, `tests/integration/test_digest_flow.py` (new), `docs/handoffs/2026-07-07-phase2-backend-close-to-cfrontend.md` (this file) |

---

## Handoff Prompt (copy from here)

```
# Resume — SignalCare Agentic Demo (Session C-frontend — admin UI scaffold + /digest page + Phase 2 CLOSE)

## Where I am

Phase 2 backend fully landed. What still ships THIS session:
- ADR-0010: Admin UI stack decisions (Next.js App Router + Tailwind + shadcn,
  dark mode strategy, provider tree)
- admin_ui/ scaffolded properly (empty currently — verify with
  `find admin_ui -type f | wc -l` — should be 0 before you start)
- /digest page — reads GET /digest/today/markdown, renders with
  react-markdown, date picker calls GET /digest/{YYYY-MM-DD}/markdown
- Live verify: `make dev` + `make demo-digest` in one shell + open
  http://localhost:3000/digest, confirm the just-generated brief renders
- TASKS.md: flip admin UI row [x], declare Phase 2 CLOSED with commit sha
- Handoff for Phase 3 kickoff (L6_adapters/relational/ Postgres arrival —
  unlocks PostgresPromptRegistry, letter-restoration of CLAUDE.md rule 6,
  L2B evidence fabric prep)

## Decisions already made (don't re-litigate)

Session C-backend locked these:

- apscheduler + AsyncIOScheduler (same asyncio loop as FastAPI, no thread
  hand-off, misfire_grace_time=30min). Job id `compliance_ops_daily_digest`
  is a stable public constant (`main._DIGEST_JOB_ID`) — a downstream admin
  tool in Phase 3+ may inspect it. Do NOT rename.
- 5 endpoints landed. All 5 depend only on `app.state.digests_dir`,
  `app.state.digest_tz`, and (for POST) `app.state.digest_agent`. No
  database, no session, no auth. Env-gate on POST is `ALLOW_ONDEMAND_DIGEST`
  (re-read every call so a demo operator can flip it without restart).
- Path pattern for `/digest/{date}` is `^\d{4}-\d{2}-\d{2}$` — 422 on
  shape mismatch (parametrized test covers 5 bad-shape cases).
- Markdown responses are `text/markdown; charset=utf-8`. The C-frontend
  page should trust that MIME and render via react-markdown.
- `/digest/today` resolves "today" in DIGEST_TZ, not server local time.
  Same tz the cron fires in — so /today always maps to the file the cron
  just wrote.
- `demo-digest` Makefile target curls POST /digest/generate and lists the
  three latest files in data/digests/. Requires ALLOW_ONDEMAND_DIGEST=true
  and ANTHROPIC_API_KEY in .env. Cost: ~$0.02 per invocation.
- Persistence contract from ADR-0008 §2 unchanged: data/digests/YYYY-MM-DD.json
  and .md. Both files, always. Same-day POST overwrites idempotently.
- data/digests/ is gitignored (runtime artifact). Test fixtures use tmp_path.
- No admin UI stack decision has been made yet. C-frontend picks the stack
  via ADR-0010; nothing about the backend forecloses App Router vs Pages,
  shadcn version, or dark-mode strategy.

## Key files to load first

- C:\SignalCareAgenticDemo\CLAUDE.md — project rules. Tech stack (line 27):
  Next.js 15 + TypeScript + shadcn/ui + Tailwind. Non-negotiable.
- C:\SignalCareAgenticDemo\TASKS.md — Phase 2 status (backend closed,
  admin UI [~] deferred to this session).
- C:\SignalCareAgenticDemo\docs\adrs\0008-compliance-ops-digest-ux.md §2:
  the /digest page is "renders the latest markdown from data/digests/*.md,
  with a date picker to browse history." Nothing else specified about UI
  shape — you have latitude on layout.
- C:\SignalCareAgenticDemo\docs\build-plan.md — Week 2 DoD includes the
  admin UI page.
- C:\SignalCareAgenticDemo\app\main.py — endpoint contract you're
  consuming. Look for `digest_router` mount and `Response(media_type=
  "text/markdown; charset=utf-8")`.
- C:\SignalCareAgenticDemo\tests\integration\test_digest_flow.py —
  46 tests covering the endpoint contract. Read the fixtures for the
  exact JSON shape and response headers.
- C:\SignalCareAgenticDemo\Makefile — demo-digest target is your live
  verify path.

## Outstanding questions (need user input)

1. **App Router vs Pages Router.** Next.js 15 defaults to App Router.
   Pages Router is stable but frozen. Recommendation: App Router. Rationale:
   Phase 5-8 add ~5 more admin pages (Feature Readiness, Agent Capability,
   Evidence Health, Prompt Registry Browser, Provider Intake Chat) — App
   Router's colocated layouts + server components + streaming will pay off
   at scale, and picking Pages now means paying a migration cost in Phase 5
   when the intake chat UI wants streaming.

2. **shadcn/ui version + primitives.** shadcn is copy-paste-vendored, so
   the version question is "which snapshot do we pin at". Recommendation:
   latest as of 2026-07-07 (v0.9.x range), vendor only the primitives
   used by /digest (`Card`, `Button`, `Select` for date picker) plus the
   toast+dialog scaffolds we'll certainly want in Phase 5-7. Add more
   primitives per-session as pages need them — don't pre-vendor.

3. **Dark mode.** Prav operates a founder brief at 06:30. Recommendation:
   yes, dark mode default with a light-mode toggle. Use next-themes +
   Tailwind dark: prefix (shadcn's canonical setup). Zero-cost architecturally.

4. **Data-fetching pattern for the date picker.** Options:
   (a) Client component that calls `fetch('/digest/{date}/markdown')` on
       date change — simple, no server route needed.
   (b) Server component per date that streams from the FastAPI backend —
       nicer perceived perf on initial load, more moving parts.
   Recommendation: (a). The demo runs on localhost; latency is
   negligible. Save server components for Phase 5's chat where they earn
   their keep.

5. **CORS.** main.py already allow_origins=["http://localhost:3000"] —
   no change needed for local. Recommendation: leave as-is, add
   FastAPI-served admin_ui build for the Phase 3+ container deploy.

6. **Live-verify expectation.** Recommendation: run `make dev`, run
   `make demo-digest` (produces today's digest), navigate to
   http://localhost:3000/digest, see the rendered brief, click yesterday
   in the date picker → 404 with "no digest generated for
   YYYY-MM-DD" (that's the correct empty state to show). Zero fabricated
   history data.

## Next concrete action

C-frontend, Phase 2 CLOSE. Realistic scope:

1. Write ADR-0010 — Admin UI stack decisions. Cover: App Router,
   Tailwind config, shadcn approach, dark mode via next-themes, dev-server
   port 3000, backend API base URL from NEXT_PUBLIC_API_URL env
   (default http://localhost:8000).
2. Scaffold admin_ui/:
   - package.json (pin exact versions — Next 15.x, React 19.x, TS 5.x,
     Tailwind 3.x)
   - tsconfig.json (strict mode)
   - next.config.mjs
   - tailwind.config.ts + postcss.config.mjs
   - components.json (shadcn config)
   - src/app/layout.tsx (dark-mode-first with next-themes provider)
   - src/app/page.tsx (root — links to /digest until other pages land)
   - src/app/globals.css (Tailwind + shadcn base)
   - src/lib/utils.ts (cn helper — shadcn convention)
   - src/components/ui/{button,card,select}.tsx (shadcn primitives)
3. src/app/digest/page.tsx:
   - Server component fetches /digest/today/markdown → renders with
     react-markdown
   - Client-side date picker (Select-based, 30-day history) calls
     /digest/{date}/markdown on change
   - Metadata strip: generated_at, guardrails counts (parse the JSON
     endpoint for that)
   - Empty state: "no digest generated for {date}" when 404
4. .env.example addition: `NEXT_PUBLIC_API_URL=http://localhost:8000`
5. Verify: `make dev` + `make demo-digest` + `cd admin_ui && npm run dev`
   + open http://localhost:3000/digest and confirm the brief renders.
6. TASKS.md: flip [~] admin UI row to [x], declare Phase 2 CLOSED
   with commit sha, remove the "Phase 2 backend closed" preface note
   (superseded).
7. Handoff for Phase 3 kickoff — L6_adapters/relational (Postgres)
   because it unlocks the letter-restoration of CLAUDE.md rule 6
   (both YAML and Postgres), the L2B evidence fabric schema, and
   Session Store.

## Working rules in effect

- ~/.claude/CLAUDE.md global standards (session bands, workflow
  classification, handoff protocol, TASKS.md sync).
- C:\SignalCareAgenticDemo\CLAUDE.md project rules — tech stack lock at
  line 27 (Next.js 15 + TypeScript + shadcn + Tailwind); do not deviate
  without an ADR (that's what ADR-0010 IS).
- Every architectural decision needs a written ADR. Stack picks belong
  in ADR-0010 before any package.json line is written.
- Prefer additive over invasive. This session ADDS admin_ui contents;
  it touches backend code only if the endpoint contract surprises you
  (it shouldn't).
- Persist future handoffs to docs/handoffs/YYYY-MM-DD-*.md.
- Run tests via ./app/.venv/Scripts/pytest.exe from repo root with
  --basetemp=.pytest-tmp (system-temp permissions issue).
- No load_dotenv; uvicorn --env-file ..\.env is the pattern (backend).
- Admin UI dev server on 3000; FastAPI on 8000. Both required for live
  verify.
- BEFORE claiming Phase 2 CLOSED: `make demo-digest` must produce a
  real brief AND the /digest page must render it. If the Anthropic call
  is stubbed at close time, Phase 2 is NOT closed.

## Persona

Direct and critical. Push back when something is wrong. Working code
beats clever abstractions. The audience is enterprise architects who
will read ADR-0001 through ADR-0010 alongside the code. C-frontend
closes Phase 2 — the whole L1→L2→L6 stack must demonstrably work
end-to-end at demo time. And **verify the scaffold state before
assuming it exists** — this session was born from that failure.
```

---

## What this handoff replaces

Predecessor: [`docs/handoffs/2026-07-07-phase2-sessions-a-b-to-session-c.md`](2026-07-07-phase2-sessions-a-b-to-session-c.md) (Sessions A+B CLOSED, Session C plan of record).

That handoff was consumed by Session C-backend, which delivered:

- **apscheduler dep** in `app/pyproject.toml`
- **main.py lifespan** — constructs `ComplianceOpsAgent` with the L2-wrapped gateway + prompt registry + PromptRenderer, then `AsyncIOScheduler(timezone=DIGEST_TZ).add_job(agent.run_daily, CronTrigger(hour=6, minute=30))` + `scheduler.start()`. Shutdown: `scheduler.shutdown(wait=False)`.
- **main.py helpers** — `_resolve_digest_tz()` (fail-open to UTC on bad env), `_ondemand_digest_allowed()` (env-gate read on every call), `_DIGEST_JOB_ID` public constant.
- **5 endpoints** at `/digest/*`:
  - `GET /digest/today` → today's JSON (404 if cron hasn't run)
  - `GET /digest/today/markdown` → today's `text/markdown`
  - `GET /digest/{YYYY-MM-DD}` → historical JSON (422 on bad shape)
  - `GET /digest/{YYYY-MM-DD}/markdown` → historical `text/markdown`
  - `POST /digest/generate` → env-gated regenerate, returns paths + caps + overrides. 403 when `ALLOW_ONDEMAND_DIGEST` unset/falsy. 500 on agent errors.
- **`Makefile` `demo-digest` target** — curls POST /digest/generate, pretty-prints JSON, lists three latest files in `data/digests/`.
- **`tests/integration/test_digest_flow.py`** — 46 tests. Endpoint contract for all 5 endpoints, env-gate boundary (5 truthy + 6 falsy values), path pattern validation (5 bad-shape cases), tz resolution helpers (default UTC, invalid → UTC, valid respected), scheduler job ID constant.
- **`TASKS.md` reconciliation** — cron row [x], full-flow test row [x], admin UI row [~] with explicit deferral note.

Test count: **198 offline** (was 151), **+46 new**. Two skipped are live-provider integrations (Ollama + Anthropic), as expected offline.

Notes NOT captured in the resume prompt (still relevant to a future auditor):

- The FastAPI startup log at `main.py` now emits `compliance_ops_scheduler_started tz=... next_run=... ondemand=...` on every boot — a lightweight forensic marker for cron/env-gate misconfigs.
- The `demo-digest` Makefile target uses `python -m json.tool` for pretty-printing rather than `jq` (which is not universally installed on Windows).
- All 5 endpoints depend only on `app.state.digests_dir`, `app.state.digest_tz`, and `app.state.digest_agent` — the C-frontend session can point them at test fixtures if it wants a stubbed demo without running the real Anthropic call.

## What the next handoff should cover

**Phase 2 CLOSED, Phase 3 kickoff.** End of C-frontend session:

- `admin_ui/` fully scaffolded with a Next.js 15 App Router + Tailwind + shadcn shell (ADR-0010 governing).
- `/digest` page renders the latest markdown, has a working date picker for history, empty state on 404.
- Live verify passed: `make dev` + `make demo-digest` + browser at http://localhost:3000/digest showing the just-generated brief.
- `TASKS.md`: Phase 2 rows all `[x]`, "Phase 2 CLOSED at commit XXXXXXX" note added, C-backend preface note removed.
- Phase 3 handoff points at `L6_adapters/relational/` (Postgres) as the first Phase 3 deliverable, because it unlocks (a) `PostgresPromptRegistry` (letter-restoration of CLAUDE.md rule 6), (b) the L2B evidence fabric schema, and (c) the session store all downstream agents depend on.

If C-frontend surfaces any surprise (App Router quirk with react-markdown SSR, shadcn version drift, dark-mode FOUC), spin an ADR-0011+ for it before landing the fix.
