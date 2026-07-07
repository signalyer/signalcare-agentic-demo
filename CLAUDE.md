# SignalCare Agentic Demo — Claude Code Operating Instructions

## Project Identity

- **Purpose:** Standalone proof-of-work demo of the SignalCare cloud-agnostic agentic architecture.
- **Audience:** Enterprise architects and AI executive leaders. Portfolio piece.
- **NOT PRODUCTION:** This is a demo. It contains synthetic data only. No real PHI ever touches this codebase.
- **Isolation:** This repo is fully standalone. `C:\ClaudeAzure` (the real SignalCare EDWP production system) must NOT be modified from work in this repo.

## Hierarchy

- Global `~/.claude/CLAUDE.md` provides universal principles.
- This file is the project source of truth.
- Architecture source of truth: `C:\ClaudeAzure\docs\agentic-architecture-consolidated-cloud-agnostic.md` (read-only reference).

## First Action Every Session

1. Read `TASKS.md` — find the current in-progress phase.
2. Read the current phase's ADR references and prior week's completion notes.
3. Verify the docker stack is healthy: `make status`.
4. Confirm which agent or layer you're working on before touching code.

## Tech Stack (locked)

- **Backend:** Python 3.12 + FastAPI + Pydantic v2 + asyncio
- **Package manager:** `uv`
- **Admin UI:** Next.js 15 + TypeScript + shadcn/ui + Tailwind
- **Database:** Postgres 16 + pgvector
- **Object store:** MinIO
- **Event bus:** NATS JetStream
- **Secrets:** HashiCorp Vault (dev mode)
- **Identity:** Keycloak
- **LLM:** Ollama (Fast tier local) + OpenRouter (Reasoning/Balanced hosted)
- **OCR:** Tesseract + docling
- **RAG:** pgvector + rank_bm25 (from scratch, no LangChain/LlamaIndex)
- **Observability:** OpenTelemetry Collector + Grafana + Loki + Tempo + Prometheus
- **Testing:** pytest + testcontainers + httpx

Do not deviate without an ADR.

## Architecture Discipline

Repo structure mirrors the architecture layers 1:1. Never place code in a layer that doesn't match its architectural role.

- L0 code goes in `app/L0_observability/`
- L2 guardrails go in `app/L2_guardrails/`
- L3 agents go in `app/L3_agents/<agent_name>/`
- L6 adapters go in `app/L6_adapters/<adapter_name>/` with a `base.py` interface and a `local.py` implementation

If you're tempted to put something at the wrong layer, stop and reconsider.

## Non-Negotiable Rules

1. **No direct database access from agents.** Agents call tools; tools call APIs; APIs use adapters. Full stop.
2. **Every request has a `trace_id`.** Propagate through L4 → L5 → L6. If it's missing, add it.
3. **BAA gate is real middleware.** Every LLM call passes through `app/L2_guardrails/baa_gate.py`. No exceptions.
4. **Every AI-generated claim carries a citation.** Un-cited claims are blocked at the guardrail layer.
5. **No cloud-vendor SDK imports outside of `app/L6_adapters/`.** No `boto3`, no `azure-sdk-*`, no `google-cloud-*` anywhere else. If found, the cloud-agnostic property is broken.
6. **Prompt registry has both YAML source of truth and Postgres runtime table.** Both must be updated together.
7. **Synthetic data only.** All names, dates, IDs, medical details are obviously fake. `Test-001`, `John TestPatient`, `GA-TEST-100001`.

## Change Discipline

Every change gets:
- A short description in the commit message (Conventional Commits format)
- If touching architecture: an ADR
- If adding a new agent or adapter: an entry in `TASKS.md`
- If touching guardrails: extra scrutiny — regression risk is high

## Testing Expectations

- Every L6 adapter has an interface test and an implementation test.
- Every L3 agent has at least one integration test that walks the full pipeline (input → guardrails → agent → tool → adapter → response).
- Every L2 guardrail has a blocking test (verifies it actually blocks bad input).
- The eval harness runs weekly via docker and produces a report in `evals/reports/`.

## When Working with LLM APIs

- Never hardcode API keys. Read from Vault via the AI Gateway adapter.
- Every LLM call logs: model, prompt hash, tokens in/out, cost, latency, trace_id.
- Every LLM response has a citation-check pass before it's returned to the caller.

## Demo Script Preservation

The demo script in `docs/demo-script.md` is the north star. When making changes, ask: does this improve the 5-minute demo walkthrough? If not, defer.

## Cross-References

- Architecture: [`ARCHITECTURE.md`](ARCHITECTURE.md)
- Build plan: [`docs/build-plan.md`](docs/build-plan.md)
- Backlog: [`TASKS.md`](TASKS.md)
- Source-of-truth architecture doc: `C:\ClaudeAzure\docs\agentic-architecture-consolidated-cloud-agnostic.md` (do not modify)

---

## Persona for Claude Code sessions on this repo

- Direct and critical. Push back when something's wrong.
- Prefer additive over invasive.
- If a proposed change breaks the cloud-agnostic property, refuse and explain why.
- Every architectural decision needs a written rationale (ADR).
- Working code beats clever abstractions.
- The audience is enterprise architects — they will read the code.
