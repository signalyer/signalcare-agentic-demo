# Handoff — Scaffold Complete → Week 1 Build

> **Generated:** 2026-07-07
> **From session:** Architecture consolidation + scaffold creation
> **To session:** Week 1 execution — infrastructure verification + AI Gateway adapter + hello-world agent
> **Copy the fenced block below into a fresh Claude Code session to resume.**

---

## Metadata

| Field | Value |
|---|---|
| Repo | `C:\SignalCareAgenticDemo\` |
| State | Scaffold complete (57 dirs, 21 files, uncommitted) |
| Phase | Phase 0 done · Phase 1 (Week 1) not started |
| Blocking action | Verify docker-compose stack comes up cleanly |
| Est. next-session duration | ~40 hours (1 week solo, full-time) |

---

## Handoff Prompt (copy from here)

```
# Resume — SignalCare Agentic Demo (Week 1 Build)

## Where I am

Scaffold complete for a standalone, portfolio-grade proof-of-work implementation
of the SignalCare cloud-agnostic agentic architecture. Repo is at
C:\SignalCareAgenticDemo — 57 directories, 21 files, docker-compose stack
defined, FastAPI skeleton written, 3 ADRs in place, 8-week phased build plan
in TASKS.md. Ready to start Week 1: Infrastructure + AI Gateway Adapter +
hello-world agent call.

The source-of-truth architecture doc lives at
C:\ClaudeAzure\docs\agentic-architecture-consolidated-cloud-agnostic.md
(READ-ONLY; do not modify — that's the SignalCare production repo).

## Decisions already made (don't re-litigate)

- Stack: Python 3.12 + FastAPI + Pydantic v2 + asyncio (see ADR-0001)
- Cloud-agnostic via adapter pattern with real local implementations (see ADR-0002)
- Postgres 16 + pgvector, MinIO, NATS JetStream, Vault dev-mode, Keycloak,
  Ollama + OpenRouter, OpenTelemetry+LGTM stack — all in docker-compose
- Admin UI: Next.js 15 + TypeScript + shadcn/ui + Tailwind (deferred to Week 5)
- No LangChain / LlamaIndex / CrewAI — roll RAG and agent orchestration from
  scratch. Architects respect discipline over framework glue.
- 5 core agents ship: Compliance/Ops (SHIPS FIRST), Document Extraction,
  Provider Intake, Reconciliation, Clinical Summary. Other 3 as stubs.
- Repo structure mirrors architecture diagram 1:1 (folders named L0_..., L1_...,
  through L7_...). This is intentional and non-negotiable.
- Synthetic data only. Never touch C:\ClaudeAzure (real production).

## Key files to load first

- C:\SignalCareAgenticDemo\CLAUDE.md — operating instructions (read fully)
- C:\SignalCareAgenticDemo\TASKS.md — phase-grouped backlog with Week 1 checklist
- C:\SignalCareAgenticDemo\ARCHITECTURE.md — layered architecture with mermaid
- C:\SignalCareAgenticDemo\docs\build-plan.md — week-by-week deliverables + DoD
- C:\SignalCareAgenticDemo\docs\adrs\0001-python-fastapi-for-demo.md
- C:\SignalCareAgenticDemo\docs\adrs\0002-cloud-agnostic-adapter-pattern.md
- C:\SignalCareAgenticDemo\docker-compose.yml — full stack
- C:\SignalCareAgenticDemo\app\pyproject.toml — Python deps (uv-managed)
- C:\SignalCareAgenticDemo\app\main.py — FastAPI skeleton with TODO markers

## Outstanding questions (need user input)

1. OpenRouter API key — provision if not already, add to .env
2. Ollama model choice — Llama 3.2 3B by default (in infra/ollama/models.txt);
   confirm laptop can run something bigger for Balanced tier
3. Whether to use Keycloak in Week 1 or defer to Week 3 (recommend defer;
   use signed JWT with a local test IdP for Week 1)

## Next concrete action

Start Week 1 Task 1: verify docker-compose stack comes up cleanly.

  cd C:\SignalCareAgenticDemo
  cp .env.example .env
  # edit .env: add OPENROUTER_API_KEY
  docker compose up -d
  make status

If any service fails, fix before proceeding. Then implement the AI Gateway
adapter (app/L6_adapters/ai_gateway/) — base.py interface + local.py (Ollama)
+ openrouter.py + router.py — and add a POST /agents/echo endpoint that
proves both providers work through the same interface.

Definition of done for Week 1:
- All docker services healthy
- Both `curl POST /agents/echo tier=fast prompt=hello` (routes to Ollama)
  and `tier=reasoning` (routes to OpenRouter) return responses
- Grafana dashboard shows both calls with latency + token counts
- pytest tests/L6_adapters/ai_gateway/ passes

## Working rules in effect

- ~/.claude/CLAUDE.md — global standards (session mgmt, git discipline,
  Claude API defaults)
- C:\SignalCareAgenticDemo\CLAUDE.md — project-specific operating instructions
  (stack locked, no cloud-vendor SDK imports outside L6_adapters, every request
  has trace_id, BAA gate is real middleware, synthetic data only)
- Cat 1-4 change control per source architecture doc
- Additive-only overlays on the existing scaffold; each new file goes in the
  layer folder that matches its architectural role

## Persona

Direct and critical. Push back when something's wrong. Prefer additive over
invasive. Every architectural decision needs a written rationale (ADR). Working
code beats clever abstractions. The audience is enterprise architects — they
will read the code.
```

---

## What this handoff replaces

Previous state: scaffold + architecture consolidation session at
`C:\SignalCareAgentics\` (scratchpad) and `C:\ClaudeAzure\docs\` (source-of-truth architecture).

Next handoff should be authored at end of Week 1 build session, at path
`docs/handoffs/YYYY-MM-DD-week1-to-week2.md`.
