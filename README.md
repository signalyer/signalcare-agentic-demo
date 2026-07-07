# SignalCare Agentic Demo

A standalone, portfolio-grade proof-of-work implementation of the SignalCare EDWP cloud-agnostic agentic architecture. Runs entirely on a laptop via `docker compose`. Built for enterprise architects and AI executive leaders to inspect, trace, and evaluate.

## What this is (and isn't)

**Is:**
- A working reference implementation of the 8-layer agentic architecture described in the SignalCare cloud-agnostic consolidated architecture doc.
- A demonstration that the architecture is real — every L6 adapter has a concrete local implementation, every guardrail is a real middleware, every citation resolves to a source document.
- An architect-legible codebase where the folder structure mirrors the architecture diagram 1:1.

**Isn't:**
- A production system.
- A clone of SignalCare EDWP (the real product lives elsewhere and is not touched by this repo).
- A single-agent chatbot demo.

## The Architecture (one-liner per layer)

| Layer | Purpose |
|---|---|
| **L0** Observability | Prompt registry, telemetry, ground-truth store, evals |
| **L1** Human Review UX | Draft review, provenance viewer, approve/edit/reject |
| **L2** Guardrails | BAA gate, PHI redactor (T1-T4), injection sentinel, adversarial verify |
| **L2A** Memory | Working / Episodic / Semantic / Procedural / Evaluation |
| **L2B** Evidence Fabric | Intake gateway, OCR, evidence objects, citation map, provenance ledger |
| **L2C** Hybrid RAG | Permission-filtered retrieval BEFORE search |
| **L3** Specialist Agents | 5 core agents (Compliance/Ops, Doc Extraction, Provider Intake, Reconciliation, Clinical Summary) |
| **L4** Orchestrator | Event router, task queue, session store, rate limiter, human handoff |
| **L5** Tool Layer | Typed adapters wrapping existing API endpoints; no direct DB access |
| **L6** Cloud-Agnostic Adapters | 8 vendor-neutral interfaces: Identity, Compute, Relational, Object, Event, Secrets, Telemetry, AI Gateway |
| **L7** Stability Map | Local implementations of workflow engine, referral service, audit |

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for full detail with diagrams.

## Quick Start

```bash
cp .env.example .env
# Fill in ANTHROPIC_API_KEY or OPENROUTER_API_KEY

make up            # docker compose up -d
make seed          # load synthetic referrals + PDFs
make demo          # 5-minute narrated walkthrough
```

Then open:
- `http://localhost:3000` — Admin Control Center (Next.js)
- `http://localhost:8000/docs` — FastAPI OpenAPI
- `http://localhost:3001` — Grafana dashboards
- `http://localhost:9001` — MinIO console
- `http://localhost:8080` — Keycloak

## Repo Structure (mirrors the architecture diagram)

```
signalcare-agentic-demo/
├── app/                    # FastAPI backend, organized by architecture layer
│   ├── L0_observability/
│   ├── L1_review_ux/
│   ├── L2_guardrails/
│   ├── L2A_memory/
│   ├── L2B_evidence/
│   ├── L2C_rag/
│   ├── L3_agents/          # One package per agent
│   ├── L4_orchestrator/
│   ├── L5_tools/
│   ├── L6_adapters/        # 8 adapter interfaces + local implementations
│   └── L7_stability/
├── admin_ui/               # Next.js Admin Control Center
├── infra/                  # docker-compose service configs
├── docs/                   # ADRs + build plan + demo script
├── data/                   # Synthetic seed + eval sets
└── evals/                  # Evaluation harness
```

## What proves the architecture is real (not vaporware)

Things an inspecting architect should look for and find:

- Every request has a `trace_id` propagated through L4 → L5 → L6, visible end-to-end in Grafana Tempo.
- Every adapter in `app/L6_adapters/` has an abstract base class with a docstring, plus a `local/` concrete implementation.
- The BAA gate is a real middleware in `app/L2_guardrails/baa_gate.py` — test it by trying to send fake PHI to an unapproved endpoint.
- Two-agent adversarial verify is a real pattern in `app/L2_guardrails/adversarial_verify.py` — used by Clinical Summary agent.
- Evidence citations in the UI are clickable and highlight the exact snippet in the source document.
- The prompt registry has both a YAML source of truth (in `app/L0_observability/prompts/`) and a Postgres runtime table.
- The evaluation harness runs a 20-example golden set with `make eval` and produces a report.

## Documentation

| Doc | Purpose |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Full layered architecture with mermaid diagrams |
| [CLAUDE.md](CLAUDE.md) | Operating instructions for AI-assisted development on this repo |
| [TASKS.md](TASKS.md) | Phase-grouped backlog — 8-week build plan with progress checkboxes |
| [docs/build-plan.md](docs/build-plan.md) | Detailed week-by-week deliverables |
| [docs/adrs/](docs/adrs/) | Architecture Decision Records |
| [docs/demo-script.md](docs/demo-script.md) | 5-minute demo walkthrough |

## License

TBD — this is a portfolio proof-of-work piece, not for production use.

## Provenance

This demo implements the architecture defined in:
- `C:\ClaudeAzure\docs\agentic-architecture-consolidated-cloud-agnostic.md`
- `C:\ClaudeAzure\docs\agentic-architecture-consolidated-cloud-agnostic.docx`

The real SignalCare EDWP production system is at `C:\ClaudeAzure` and is **not modified by this demo**.
