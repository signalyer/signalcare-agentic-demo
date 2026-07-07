# SignalCare Agentic Demo — Task Ledger

> Last reconciled: 2026-07-07 (Phase 1 CLOSED — live verify passed on both tiers; ADRs 0003 docker deferral + 0004 direct SDKs over OpenRouter)
> Format: Phase-grouped (see global CLAUDE.md `PROJECT-TASKS.md` template)
> Status: `[ ]` open · `[x]` done · `[~]` in progress · `[!]` blocked

---

## Phase 0 — Scaffold (session 2026-07-07)

- [x] Create repo directory structure (57 directories)
- [x] Write `README.md`, `ARCHITECTURE.md`, `CLAUDE.md`, `TASKS.md`
- [x] Write `docker-compose.yml`, `.env.example`, `Makefile`, `pyproject.toml`, `.gitignore`
- [x] Write FastAPI `main.py` skeleton + `Dockerfile`
- [x] Write initial ADRs (0001 Python/FastAPI, 0002 Adapter pattern) + template
- [x] Write `docs/build-plan.md` + `docs/demo-script.md`
- [x] Write `infra/postgres/init.sql` + `infra/ollama/models.txt`
- [x] Write L3 agents README + L6 adapters README (conventions)
- [x] Author handoff file `docs/handoffs/2026-07-07-scaffold-to-week1.md`
- [x] `git init` and initial commit (root-commit `7c61907`, 2026-07-07)
- [x] ~~Confirm docker-compose stack comes up cleanly~~ → **deferred to Phase 3 via ADR-0003** (no container runtime on Week 1 host machine; native Ollama covers Week 1 needs)

---

## Phase 1 — Week 1: AI Gateway Adapter + Hello World Agent

**Note (ADR-0003):** Docker-compose stack bring-up moved to Phase 3. Week 1 uses **native Ollama on Windows** (`http://localhost:11434`) + OpenRouter (hosted). Everything else in the compose stack is not on the Week 1 code path.

- [x] Install native Ollama on Windows + pull `llama3.2:3b` (winget silent install, model live at localhost:11434)
- [x] Implement `app/L6_adapters/ai_gateway/base.py` interface (`complete`, `stream`) — commit 7c61907
- [x] Implement `app/L6_adapters/ai_gateway/local.py` — Ollama concrete — commit 7c61907
- [x] ~~Implement `openrouter.py`~~ → **superseded by `anthropic_gateway.py` per ADR-0004** (direct SDK; OpenRouter 402 no-credits triggered pivot)
- [x] Implement `app/L6_adapters/ai_gateway/anthropic_gateway.py` — Anthropic direct SDK concrete (Balanced=Sonnet, Reasoning=Opus). Handles `system` split + `temperature` deprecation sentinel — ADR-0004
- [x] Wire tier-based routing in `app/L6_adapters/ai_gateway/router.py` (Fast → Ollama, Balanced/Reasoning → Anthropic) — commit 7c61907, updated per ADR-0004
- [x] Add `/agents/echo` endpoint in FastAPI `main.py` (accepts `tier` + `prompt`, returns text + model + provider + latency + token counts) — commit 7c61907
- [x] **Hello-world agent call live-verified on all three tiers** (Fast: llama3.2:3b 601ms warm; Balanced: claude-sonnet-4-6 1091ms; Reasoning: claude-opus-4-7 1603ms) — this closes the ADR-0002 proof-point empirically
- [x] Unit tests `tests/unit/test_ai_gateway.py` — 13/13 passing offline (added Anthropic adapter internals)
- [x] Integration tests `tests/integration/test_ai_gateway_live.py` — 3/3 passing live (Ollama + Anthropic + same-interface proof-point)
- [x] Add `make status-lite` target (native Ollama ping + OpenRouter reachability check) — commit 7c61907
- [~] ~~Grafana dashboard #1: request rate, latency, model breakdown~~ → **moved to Phase 3** (batched with the other three dashboards; interim visibility via `structlog` stdout)

### Phase 1 CLOSED: 2026-07-07. All Week 1 code deliverables live-verified. Ready for Phase 2.

### Open design point surfaced this session (blocks Phase 2 wiring)
- [ ] Env loading path: uvicorn `--env-file` (A, currently in effect) vs centralised `pydantic-settings` `Settings` loaded once at startup (B, better fit for Phase 3 when Postgres/NATS/Vault creds land). Live verify uses A via `uvicorn main:app --env-file ..\.env`. Document in README or migrate to B before Phase 3 credentials wiring.

## Phase 2 — Week 2: L1 API + L2 Guardrails + Agent #8 Compliance/Ops (Founder Mode)

- [ ] Implement `app/L2_guardrails/baa_gate.py` — real middleware that blocks PHI-bearing calls to unapproved endpoints
- [ ] Implement `app/L2_guardrails/phi_redactor.py` — T1-T4 tiered redaction
- [ ] Implement `app/L2_guardrails/injection_sentinel.py` — prompt injection classifier
- [ ] Implement `app/L3_agents/compliance_ops/` — Founder Mode digest agent
- [ ] Data sources for digest: docker stats, Postgres audit table, fake `hardening_status.json`
- [ ] Prompt: registered in YAML at `app/L0_observability/prompts/compliance_ops_digest.yaml`
- [ ] Prompt registry table + insert on startup
- [ ] Cron job: daily digest at 06:30
- [ ] Simple digest page in Admin UI
- [ ] Test: full flow from cron trigger → LLM → digest email/UI

## Phase 3 — Week 3: Remaining 7 L6 Adapters + L4 Orchestrator + Telemetry

- [ ] `L6_adapters/identity/` — Keycloak OIDC adapter
- [ ] `L6_adapters/compute/` — docker-compose adapter (health/restart interface)
- [ ] `L6_adapters/relational/` — Postgres adapter with pgvector
- [ ] `L6_adapters/object_store/` — MinIO S3-compatible adapter
- [ ] `L6_adapters/event_bus/` — NATS JetStream adapter
- [ ] `L6_adapters/secrets/` — Vault dev-mode adapter
- [ ] `L6_adapters/telemetry/` — OpenTelemetry adapter (traces + metrics + logs)
- [ ] `L4_orchestrator/` — asyncio task queue + event router + session store
- [ ] `L0_observability/prompt_registry/` — hash-versioned prompt storage
- [ ] Grafana dashboards: per-agent latency, cost, override rate, adapter health
- [ ] Traces visible in Tempo end-to-end (L4 → L5 → L6)

## Phase 4 — Week 4: L2B Evidence Fabric + L2C RAG + Agent #3 Document Extraction

- [ ] Postgres schema: `evidence_objects`, `fact_records`, `citation_map`, `provenance_ledger`
- [ ] Intake gateway: MinIO upload → NATS `DocumentUploaded` event
- [ ] Malware scan stub + PHI classification (T1-T4 estimate)
- [ ] Fingerprint / dedup by content hash
- [ ] Taxonomy classifier (LLM-based)
- [ ] OCR pipeline: tesseract + docling for layout
- [ ] Confidence scoring per field
- [ ] `app/L2C_rag/` — pgvector index, permission filter BEFORE search, hybrid retrieval, reranker
- [ ] `app/L3_agents/document_extraction/` — full agent with citation resolution
- [ ] Verification Workbench UI page
- [ ] End-to-end: upload PDF → OCR → evidence object created → citations resolvable

## Phase 5 — Week 5: Agent #1 Provider Intake + Session Store + Feature Readiness UI

- [ ] `app/L3_agents/provider_intake/` — conversational tool-calling agent
- [ ] Session persistence in Postgres via relational adapter
- [ ] Chat UI page in Admin UI
- [ ] Tool: `update_field`, `validate_form`, `save_draft`, `submit_referral`
- [ ] Human confirmation UI: shows collected data + confirm/edit before submit
- [ ] Admin UI: Feature Readiness Registry (CRUD)
- [ ] Seed: `capability_key`, `status`, `evidence`, `owner`, `last_verified` for 10 sample capabilities
- [ ] Test: full intake flow from chat start to referral persisted

## Phase 6 — Week 6: Agent #4 Reconciliation + L2A Memory + Agent Capability Matrix UI

- [ ] `app/L2A_memory/working/` — Redis-backed session memory
- [ ] `app/L2A_memory/episodic/` — Postgres durable interaction log with PHI-scoped policy
- [ ] `app/L2A_memory/semantic/` — pgvector store for stable facts
- [ ] `app/L3_agents/reconciliation/` — cross-source conflict detection agent
- [ ] Conflict Panel UI with citation links
- [ ] Test: seed 2 conflicting extracted docs, verify agent surfaces conflict with citations
- [ ] Admin UI: Agent Capability Matrix (read-only view of all 5 agents with their tools, PHI status, HITL gates)

## Phase 7 — Week 7: Agent #6 Clinical Summary + Adversarial Verify + Evidence/RAG Health UI

- [ ] `app/L3_agents/clinical_summary/` — Reasoning-tier agent
- [ ] `app/L2_guardrails/adversarial_verify.py` — two-agent verify pattern
- [ ] Clinical sign-off gate at API boundary
- [ ] Provenance viewer: click citation → open source PDF with snippet highlighted
- [ ] Admin UI: Evidence/RAG Health dashboard (index freshness, OCR failure rate, citation coverage, docs needing verification)
- [ ] End-to-end happy path: referral → docs → extraction → reconciliation → clinical summary → RN sign-off
- [ ] Test: adversarial verify catches a low-confidence output and returns it to primary

## Phase 8 — Week 8: Eval Harness + Prompt Registry Browser + Demo Script + Polish

- [ ] `evals/golden_set.json` — 20 examples across all 4 flagship agents
- [ ] `evals/run_evals.py` — pytest-style runner with report generation
- [ ] Weekly eval cron via docker
- [ ] Admin UI: Prompt Registry Browser (list all prompts, show versions, view YAML source, view Postgres runtime record)
- [ ] `docs/demo-script.md` — 5-minute narrated walkthrough
- [ ] Record demo video (optional)
- [ ] README polish: add screenshots, refine setup instructions
- [ ] Final ADRs written for all major decisions
- [ ] Cleanup pass on TODO/FIXME comments

---

## Backlog (post-Phase 8, not scoped)

- Multi-tenant scoping (2+ seeded tenants)
- Remaining 3 agents implemented (Completeness, Eligibility, Packet Assembly)
- Workflow safety controls (lint, regression, impact analysis, rollback)
- Rule Test Console
- Deployment Safety UI module
- Import/export for admin config
- Kubernetes deployment (optional — proves the cloud-agnostic property under load)

---

## Blockers / Open Questions

1. Which OpenRouter model IDs to use for Reasoning/Balanced tiers — pick during Week 1 setup.
2. Ollama model selection depending on user's local GPU capability — pick during Week 1 setup.
3. Whether to use Keycloak or skip it in favor of JWT+test-IdP (Week 1 decision).
