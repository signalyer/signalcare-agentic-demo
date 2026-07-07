# Demo Script — 5-Minute Walkthrough

> Written incrementally as agents ship. Final polish in Week 8.

## Setup (30 seconds)

1. Open browser tabs:
   - `http://localhost:3000` — Admin Control Center
   - `http://localhost:3001` — Grafana dashboards
   - `http://localhost:8000/docs` — FastAPI OpenAPI

2. Terminal: `docker compose ps` shows all services green.

3. Optional: `curl http://localhost:8000/` shows architecture summary.

## Act 1 — The Architecture Is Real (60 seconds)

- Open the repo in an editor. Show the folder structure: `L0_observability/`, `L1_review_ux/`, ..., `L7_stability/`.
- Say: "The folder structure mirrors the architecture diagram 1:1. Every layer is a real Python package."
- Open `app/L6_adapters/ai_gateway/base.py`. Show the abstract interface.
- Open `app/L6_adapters/ai_gateway/local.py` (Ollama) and `openrouter.py`. Show two concrete implementations of the same interface.
- Say: "The AI Gateway routes Fast-tier calls to Ollama locally, Reasoning-tier calls to OpenRouter. Same interface, deployment-time binding."

## Act 2 — Founder Ops Copilot (Ships First, 60 seconds)

- Open `http://localhost:3000/digest`.
- Show today's founder digest: docker resource usage, audit summary, cost, hardening progress.
- Say: "This is Agent #8 in Founder Mode. Non-PHI, ships pre-BAA, saves 3-5 hours a week of manual ops review."
- Open Grafana Tempo. Show the trace of the digest run: L4 orchestrator → L5 tools → L6 adapters (relational, telemetry, ai_gateway).

## Act 3 — Evidence Fabric (90 seconds) — the flagship insight

- Upload `data/seed/synthetic_referral_003.pdf` via the Admin UI.
- Watch: MinIO stores the object → NATS emits event → Document Extraction agent fires.
- Show the Verification Workbench: extracted fields with confidence scores and citations.
- Click a citation. Source PDF opens with the exact snippet highlighted.
- Say: "Documents aren't files. They're governed evidence objects. Every AI-generated claim resolves to a specific document, version, page, and snippet."

## Act 4 — Reconciliation (60 seconds)

- Show a case with two conflicting documents (different DOB on referral vs medical record).
- Reconciliation agent surfaces the conflict.
- Show the Conflict Panel with citations to both source documents.
- Resolve as staff. Field updates propagate through the tool layer.
- Say: "Cross-source conflicts require judgment, not rules. Agent surfaces the conflict with evidence; human decides."

## Act 5 — Clinical Summary + Adversarial Verify (60 seconds)

- Open a case at RN Review state.
- Trigger Clinical Summary agent (Reasoning tier via OpenRouter → Claude Opus).
- Show the draft summary with citations.
- Show the adversarial verifier's pass: either accepts or refutes.
- If refuted: back to primary for revision. Loop until accepted or timeout.
- RN signs off. Summary persisted with full provenance chain.
- Say: "Clinical outputs go through two-agent verify plus named human sign-off. No autonomous clinical decisions ever."

## Act 6 — Admin Control Center (45 seconds)

Whistle-stop tour of the Admin UI:
- Feature Readiness Registry — every capability with evidence and last-verified date.
- Agent Capability Matrix — all 5 agents × tools × PHI × HITL gates × model tiers.
- Evidence/RAG Health — index freshness, OCR failures, citation coverage.
- Prompt Registry Browser — YAML source and Postgres runtime for every prompt.

## Act 7 — Evals (30 seconds)

- Terminal: `make eval`
- Show the report: per-agent human override rate, citation accuracy, hallucination flag rate.
- Say: "Every prompt/model change goes through this before promotion. This is what turns an agent into a production system."

## Close (15 seconds)

- Say: "Everything you saw runs on this laptop via docker-compose. Zero cloud dependencies. Every L6 adapter has a real local implementation. Migration to any cloud is one concrete implementation per adapter, no agent or business-logic changes."
- Show the ADRs folder.
- Fin.
