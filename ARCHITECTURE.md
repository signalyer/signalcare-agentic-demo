# Architecture

Full layered architecture reference for the SignalCare Agentic Demo. Mirrors the source-of-truth architecture at `C:\ClaudeAzure\docs\agentic-architecture-consolidated-cloud-agnostic.md`.

## Layered View

```mermaid
flowchart TB
    subgraph L0["L0 · Observability, Evals, Feedback"]
        T[Telemetry Pipeline]
        PR[Prompt Registry]
        GT[Ground-Truth Store]
    end

    subgraph L1["L1 · Human Review UX"]
        DP[Draft Review Panel]
        PV[Provenance Viewer]
        AR[Approve · Edit · Reject]
    end

    subgraph L2["L2 · Guardrails & Policy"]
        BAA[BAA/DPA Gate]
        PhR[PHI Redactor · T1-T4]
        TA[Two-Agent Adversarial Verify]
        SG[Clinical Sign-Off Gate]
        PI[Prompt-Injection Sentinel]
    end

    subgraph L2A["L2A · Memory & Context Fabric"]
        WM[Working · session/TTL]
        EM[Episodic · durable]
        SM[Semantic · vector/graph]
        Pro[Procedural · SOPs]
        EvM[Evaluation · overrides]
    end

    subgraph L2B["L2B · Evidence Fabric"]
        DI[Intake Gateway]
        OCR[OCR / Layout]
        Tax[Taxonomy]
        Ev[Evidence Object Model]
        VW[Verification Workbench]
    end

    subgraph L2C["L2C · Hybrid RAG"]
        PermF[Permission Filter BEFORE retrieval]
        Hyb[Vector + Keyword + Metadata + Graph]
        RR[Reranker]
        CB[Context Builder + Citations]
    end

    subgraph L3["L3 · Specialist Agents"]
        A[5 core + 3 stubs]
    end

    subgraph L4["L4 · Multi-Agent Orchestrator"]
        Rt[Event Router]
        Q[Task Queue]
        Sess[Session Store]
        RL[Rate Limiter]
        HH[Human Handoff]
    end

    subgraph L5["L5 · Agent Tool Layer"]
        TR[Tool Registry]
    end

    subgraph L6["L6 · Cloud-Agnostic Adapters"]
        A6[8 vendor-neutral interfaces]
    end

    subgraph L7["L7 · Stability Map (local)"]
        WE[Workflow Engine]
        RC[Referral Service]
        AS[Audit Service]
    end

    L0 --> L1 --> L2 --> L3
    L2A --> L3
    L2B --> L2C --> L3
    L3 --> L4 --> L5 --> L6 --> L7
```

## L6 Adapter Contracts

Every external-platform dependency is a well-defined interface. The demo ships a local implementation of each; production would bind a different implementation at deployment time.

| Adapter | Local Implementation (this demo) | Interface File |
|---|---|---|
| Identity Provider | Keycloak (OIDC) | `app/L6_adapters/identity/base.py` |
| Compute Runtime | docker-compose | `app/L6_adapters/compute/base.py` |
| Relational Store | Postgres 16 + pgvector | `app/L6_adapters/relational/base.py` |
| Object Store | MinIO (S3-compatible) | `app/L6_adapters/object_store/base.py` |
| Event Bus | NATS JetStream | `app/L6_adapters/event_bus/base.py` |
| Secrets Vault | HashiCorp Vault (dev mode) | `app/L6_adapters/secrets/base.py` |
| Telemetry Sink | OpenTelemetry → LGTM stack | `app/L6_adapters/telemetry/base.py` |
| AI Model Gateway | Ollama (Fast tier) + OpenRouter (Reasoning + Balanced) | `app/L6_adapters/ai_gateway/base.py` |

## Model Tier Taxonomy (vendor-neutral)

| Tier | Local | API | Used By |
|---|---|---|---|
| Reasoning | Llama 3.3 70B (if GPU) | Claude Opus / GPT-5 via OpenRouter | Clinical Summary, Document Extraction, Packet Assembly |
| Balanced | Qwen 2.5 14B | Claude Sonnet via OpenRouter | Provider Intake, Reconciliation, Compliance/Ops digest |
| Fast | Llama 3.2 3B (CPU-fine) | Claude Haiku via OpenRouter | Completeness Checker, Eligibility Assist, Anomaly classification |

## Agent Catalog (5 core + 3 stubs for the demo)

| # | Agent | Model Tier | Ships in Demo | Trigger |
|---|---|---|---|---|
| 1 | Provider Intake Assistant | Balanced | **Full** | Portal new-referral |
| 2 | Completeness Checker | Fast | Stub | Submit intent |
| 3 | Document Extraction Agent | Reasoning | **Full** | Doc uploaded |
| 4 | Reconciliation Agent | Balanced | **Full** | Post-extraction |
| 5 | Eligibility Verification | Fast/Balanced | Stub | State = Eligibility |
| 6 | Clinical Summary Agent | Reasoning | **Full** | Screening/Triage/Review |
| 7 | Packet Assembly Agent | Reasoning | Stub | Ready for AHS |
| 8 | Compliance/Ops (Founder Mode) | Balanced+Fast | **Full · SHIPS FIRST** | Daily digest schedule |

## Trust Zones

```mermaid
flowchart LR
    ZA[Zone A: Provider/Staff UI] --> ZB[Zone B: App Services]
    ZB --> ZC[Zone C: Regulated Data]
    ZB -. approved + minimized only .-> ZD[Zone D: External AI Providers]
    ZC -. no raw PHI without gate .-> ZD
    style ZD fill:#fecaca,stroke:#dc2626,stroke-width:3px
```

In demo mode with fully synthetic data, no real PHI is ever in the system. The BAA gate still functions to prove the enforcement pattern.

## Cross-References

- [`C:\ClaudeAzure\docs\agentic-architecture-consolidated-cloud-agnostic.md`](file:///C:/ClaudeAzure/docs/agentic-architecture-consolidated-cloud-agnostic.md) — full architecture source of truth
- [`C:\ClaudeAzure\docs\agentic-architecture-consolidated-cloud-agnostic.docx`](file:///C:/ClaudeAzure/docs/agentic-architecture-consolidated-cloud-agnostic.docx) — Word companion
- [`docs/adrs/`](docs/adrs/) — Architecture Decision Records
- [`docs/build-plan.md`](docs/build-plan.md) — 8-week build plan
