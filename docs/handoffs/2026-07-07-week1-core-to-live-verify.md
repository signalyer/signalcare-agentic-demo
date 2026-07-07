# Handoff — Week 1 Core Committed → Live Verify → Phase 2

> **Generated:** 2026-07-07 (second session of the day)
> **From session:** ADR-0003 authored, L6 AI Gateway adapter shipped, unit tests green, 2 commits landed
> **To session:** Native-Ollama install → live `/agents/echo` verification → env-loading decision → Phase 2 kickoff
> **Copy the fenced block below into a fresh Claude Code session to resume.**

---

## Metadata

| Field | Value |
|---|---|
| Repo | `C:\SignalCareAgenticDemo\` (initialized, branch `main`, no remote yet) |
| State | Phase 1 code done + committed; live verification pending Ollama install |
| Head | `a5c2a04 Docs: reconcile TASKS.md after root commit 7c61907` |
| Blocking action | User installs Ollama; then confirm env-loading design choice (A vs B) |
| Est. next-session duration | ~15 min live verify, then ~5 hours to Phase 2 kickoff |

---

## Handoff Prompt (copy from here)

```
# Resume — SignalCare Agentic Demo (post Week 1 core commit)

## Where I am

Scaffold + Phase 1 core code both committed on branch main at C:\SignalCareAgenticDemo.
Two commits: 7c61907 (scaffold + L6 AI Gateway adapter + /agents/echo endpoint +
ADR-0003 docker deferral + Makefile status-lite/dev/test-lite targets) and a5c2a04
(TASKS.md reconciliation). 12/12 unit tests pass offline. 3 integration tests are
skip-guarded pending live providers. No remote configured; no pushes.

Python 3.14.3 + uv are installed. app/.venv is populated (uv sync --extra dev has run).
docker is NOT installed on this machine and stays deferred to Phase 3 per ADR-0003.
Ollama is NOT installed yet. .env exists with real OPENROUTER_API_KEY but OLLAMA_HOST
still points at the docker-compose service name http://ollama:11434 (must be swapped to
http://localhost:11434 for native Ollama).

## Decisions already made (don't re-litigate)

- Docker-compose bring-up is deferred to Phase 3 (ADR-0003). Don't try to run `make up`
  or `docker compose ps`. Use `make status-lite`, `make dev`, `make test-lite` instead.
- AI Gateway abstraction has three concrete pieces: OllamaGateway (Fast, native localhost),
  OpenRouterGateway (Balanced/Reasoning, hosted OpenAI-compat), TieredAIGateway (composes
  and dispatches by Tier). Interface is `complete` + `stream` + `supports_tier`. Tool-calling
  will be added in Phase 2 when the first tool-using agent needs it — do NOT add speculatively.
- Env is currently read via bare os.getenv. NO load_dotenv is wired. This is intentional
  pending a design decision (see Outstanding questions).
- Tests live at repo-root ./tests. Canonical pytest config is pytest.ini at repo root
  (not in app/pyproject.toml). pythonpath = app so tests import L6_adapters exactly as
  main.py does.

## Key files to load first

- C:\SignalCareAgenticDemo\CLAUDE.md — project operating rules
- C:\SignalCareAgenticDemo\TASKS.md — Phase 1 remainders + Phase 2 checklist (Phase 1 items
  now marked done with commit shas; env-loading design point is logged as open)
- C:\SignalCareAgenticDemo\docs\adrs\0003-defer-container-runtime-to-phase-3.md
- C:\SignalCareAgenticDemo\app\L6_adapters\ai_gateway\ (base.py, local.py, openrouter.py,
  router.py, __init__.py)
- C:\SignalCareAgenticDemo\app\main.py — /agents/echo + lifespan wiring
- C:\SignalCareAgenticDemo\pytest.ini + tests/conftest.py
- C:\SignalCareAgenticDemo\.env — real OpenRouter key present; OLLAMA_HOST needs swap
- C:\SignalCareAgenticDemo\docs\handoffs\2026-07-07-scaffold-to-week1.md (predecessor)

## Outstanding questions (need user input)

1. Env-loading design (blocks Phase 2): (A) uvicorn --env-file ../.env in `make dev` +
   docs, recommended for Week 1 speed; or (B) centralise on pydantic-settings Settings
   loaded once at startup, better fit for Phase 3 credential wiring. TASKS.md logs this.
2. Ollama model choice — llama3.2:3b assumed. Confirm or size up.

## Next concrete action

Step 1 — User installs Ollama (one-time, ~10 min):
  winget install --id Ollama.Ollama --accept-source-agreements --accept-package-agreements
  ollama pull llama3.2:3b
  curl http://localhost:11434/api/tags   # sanity

Step 2 — User edits .env: OLLAMA_HOST=http://localhost:11434

Step 3 — Live verify (assistant drives):
  cd C:\SignalCareAgenticDemo\app
  .\.venv\Scripts\uvicorn.exe main:app --env-file ..\.env --reload --port 8000
  # in another shell:
  curl -X POST http://localhost:8000/agents/echo -H "Content-Type: application/json" -d '{"tier":"fast","prompt":"sky color?"}'
  curl -X POST http://localhost:8000/agents/echo -H "Content-Type: application/json" -d '{"tier":"reasoning","prompt":"sky color?"}'
  # then:
  .\.venv\Scripts\python.exe -m pytest tests/integration -v   # was 3 skipped; expect 3 passed

If both curl calls return with different `provider` fields and integration tests flip green,
ADR-0002 proof-point is validated. Commit as Phase 1 close.

Step 4 — Decide env-loading path A/B; if B, implement app/config.py Settings before starting
Phase 2 work. Then start Phase 2 per TASKS.md (L2 guardrails + Compliance/Ops agent).

## Working rules in effect

- ~/.claude/CLAUDE.md global standards
- C:\SignalCareAgenticDemo\CLAUDE.md project rules (no cloud SDK outside L6_adapters, every
  request has trace_id, synthetic data only, BAA gate becomes real middleware in Phase 2)
- Persist future handoffs to docs/handoffs/YYYY-MM-DD-*.md (never inline-only)
- Prefer additive over invasive; every architectural decision needs a written ADR

## Persona

Direct and critical. Push back when something is wrong. Working code beats clever
abstractions. The audience is enterprise architects — they will read the code.
```

---

## What this handoff replaces

Predecessor: `docs/handoffs/2026-07-07-scaffold-to-week1.md` (Phase 0 scaffold complete → Week 1 code build).

## What the next handoff should cover

Live verification passing + env-loading decision landed + Phase 2 first Compliance/Ops middleware sketched. Author at `docs/handoffs/YYYY-MM-DD-phase1-close-to-phase2.md`.
