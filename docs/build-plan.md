# Build Plan — 8 Weeks

Detailed week-by-week execution plan. Each week ships a demoable slice. If a week overruns by ~30%, absorb into the next week and cut the last item.

## Week 1 — Infrastructure + AI Gateway + Hello World

**Goal:** `docker compose up` produces a healthy stack; hello-world agent call works through the AI Gateway adapter for both Ollama and OpenRouter/Claude.

**Deliverables:**
- All docker services healthy (postgres, minio, nats, vault, keycloak, ollama, otel, loki, tempo, prometheus, grafana, app)
- `app/L6_adapters/ai_gateway/base.py` — abstract interface with `complete()`, `stream()`, `with_tools()`
- `app/L6_adapters/ai_gateway/local.py` — Ollama concrete implementation
- `app/L6_adapters/ai_gateway/openrouter.py` — OpenRouter concrete (calls Claude/GPT via unified API)
- `app/L6_adapters/ai_gateway/router.py` — routes to concrete based on tier (Fast → local, Balanced/Reasoning → openrouter)
- `/agents/echo?tier={fast|balanced|reasoning}&prompt=...` endpoint proves the routing works
- Grafana dashboard #1: request rate, latency histogram, model breakdown

**Definition of done:** Both `curl http://localhost:8000/agents/echo?tier=fast&prompt=hello` and `...tier=reasoning...` return responses; Grafana shows both calls in a dashboard.

## Week 2 — L2 Guardrails + Agent #8 Compliance/Ops (Founder Mode) — SHIPS FIRST

**Goal:** Non-PHI agent that produces a real daily digest and blocks would-be PHI leaks.

**Deliverables:**
- `app/L2_guardrails/baa_gate.py` — middleware; refuses model calls with `phi_present=True` if vendor not in `APPROVED_PHI_VENDORS`
- `app/L2_guardrails/phi_redactor.py` — regex + Presidio-style entity extraction; T1-T4 tier tagging
- `app/L2_guardrails/injection_sentinel.py` — classifier for prompt-injection patterns in user content
- `app/L3_agents/compliance_ops/` — Founder Mode digest agent
- Data sources: docker stats via `psutil`, Postgres audit table, `data/seed/hardening_status.json`
- Prompt in `app/L0_observability/prompts/compliance_ops_digest.yaml`
- Prompt registry table + on-startup sync from YAML
- Cron: `apscheduler` triggers digest at 06:30 local
- Simple `/digest/today` endpoint returns the latest digest
- Test: BAA gate blocks a request with `phi_present=True` and unapproved vendor

**Definition of done:** `make demo-digest` produces a real-looking founder brief; `pytest tests/L2_guardrails/` passes with the BAA blocking test.

## Week 3 — Remaining 7 L6 Adapters + L4 Orchestrator + End-to-End Tracing

**Goal:** All 8 adapters implemented; every request has a trace_id visible in Tempo end-to-end.

**Deliverables:**
- `L6_adapters/identity/` — Keycloak OIDC adapter
- `L6_adapters/compute/` — docker-compose health/restart adapter
- `L6_adapters/relational/` — Postgres + pgvector adapter with connection pool
- `L6_adapters/object_store/` — MinIO adapter with pre-signed URLs
- `L6_adapters/event_bus/` — NATS JetStream adapter with subject-based routing
- `L6_adapters/secrets/` — Vault dev-mode adapter
- `L6_adapters/telemetry/` — OTel adapter (traces + metrics + logs)
- `L4_orchestrator/` — asyncio task queue + event router + session store
- OpenTelemetry instrumentation on FastAPI, httpx, asyncpg
- Grafana dashboards: adapter health, per-agent latency, per-tier cost
- Traces in Tempo show L4 → L5 → L6 flow with span attributes

**Definition of done:** Every adapter has an interface test + implementation test; Tempo shows end-to-end traces for a `/agents/echo` call spanning ≥6 spans.

## Week 4 — L2B Evidence Fabric + L2C RAG + Agent #3 Document Extraction

**Goal:** Upload a PDF, get back evidence objects with resolvable citations.

**Deliverables:**
- Postgres schema: `evidence_objects`, `fact_records`, `citation_map`, `provenance_ledger` (in `infra/postgres/init.sql`)
- `L2B_evidence/intake_gateway.py` — MinIO upload trigger → NATS `DocumentUploaded` event
- Malware scan stub (accept-all in demo)
- PHI classification pre-filter (LLM-based, tags T1-T4 estimate)
- Fingerprint / dedup by SHA256 content hash
- `L2B_evidence/taxonomy.py` — document type classifier
- OCR pipeline: tesseract for text + docling (or pypdf) for layout
- Confidence scoring per extracted field
- `L2C_rag/permission_filter.py` — filters BEFORE search; applies tenant/referral/member/role
- `L2C_rag/hybrid.py` — pgvector cosine + BM25 keyword combined
- `L2C_rag/reranker.py` — verification-status × recency × confidence × relevance
- `L3_agents/document_extraction/` — Reasoning-tier agent using OpenRouter
- Verification Workbench page in Admin UI

**Definition of done:** Upload `data/seed/sample_referral.pdf` → agent creates evidence object → citations resolvable in UI → click a citation, see the source snippet highlighted.

## Week 5 — Agent #1 Provider Intake + Session Store + Feature Readiness UI

**Goal:** Conversational intake creates a real draft referral.

**Deliverables:**
- `L3_agents/provider_intake/` — tool-calling conversational agent
- Tools: `update_field`, `validate_form`, `save_draft`, `submit_referral`
- Session persistence in `sessions` Postgres table
- Chat UI page in Admin UI (React + shadcn)
- Human confirmation UI: shows collected fields + confirm/edit before submit
- Feature Readiness Registry: schema + CRUD API + Admin UI page
- Seed 10 sample capabilities with `last_verified` timestamps

**Definition of done:** Chat with the agent for 3 minutes → referral persisted in DB → visible in Admin UI referral list.

## Week 6 — Agent #4 Reconciliation + L2A Memory + Agent Capability Matrix UI

**Goal:** Cross-source conflict detection with citation panel.

**Deliverables:**
- `L2A_memory/working/` — Redis-backed session memory
- `L2A_memory/episodic/` — Postgres durable interaction log
- `L2A_memory/semantic/` — pgvector store for stable facts (providers, counties, procedures)
- `L3_agents/reconciliation/` — cross-source conflict detection
- Conflict Panel UI with citation links to both source documents
- Admin UI: Agent Capability Matrix (read-only) showing all 5 agents × tools × PHI × HITL × model tier × flag

**Definition of done:** Seed 2 conflicting synthetic PDFs → agent surfaces DOB conflict with citations to both docs → staff resolves via UI → referral field updated.

## Week 7 — Agent #6 Clinical Summary + Adversarial Verify + Evidence/RAG Health UI

**Goal:** Reasoning-tier clinical summarization with two-agent verification and clinical sign-off.

**Deliverables:**
- `L3_agents/clinical_summary/` — Reasoning-tier agent
- `L2_guardrails/adversarial_verify.py` — spawns a second verifier agent; if refuted, returns to primary for revision
- Clinical sign-off gate at controller layer: `SignedByUserId` required for persistence
- Provenance viewer: click citation → open source PDF with snippet highlighted
- Admin UI: Evidence/RAG Health dashboard (index freshness, OCR failure rate, citation coverage, docs needing verification, fact extraction rate)

**Definition of done:** End-to-end happy path — referral → docs → extraction → reconciliation → clinical summary → adversarial verify passes → RN signs off → all persisted with full provenance chain.

## Week 8 — Eval Harness + Prompt Registry Browser + Demo Script + Polish

**Goal:** Everything eval-able and demoable.

**Deliverables:**
- `evals/golden_set.json` — 20 examples covering all 4 flagship agents
- `evals/run_evals.py` — pytest-style runner; produces JSON report
- Weekly eval cron via docker (or manual `make eval`)
- Admin UI: Prompt Registry Browser (list all prompts, versions, YAML source, Postgres runtime record)
- `docs/demo-script.md` — 5-minute narrated walkthrough
- README polish with screenshots
- Final ADRs for all major decisions
- Cleanup pass on TODO/FIXME
- Optional: recorded video walkthrough

**Definition of done:** `make eval` produces a report; `make demo` runs a 5-minute narrated walkthrough; repo is portfolio-ready.

## Post-Week-8 Backlog

- Remaining 3 agents (Completeness, Eligibility, Packet Assembly)
- Workflow safety controls (lint, regression, impact analysis, rollback)
- Rule Test Console
- Multi-tenant scoping
- Kubernetes deployment (proves cloud-agnostic under load)
