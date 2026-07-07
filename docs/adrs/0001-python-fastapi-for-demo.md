# ADR-0001 — Python 3.12 + FastAPI for the Demo (Not .NET)

**Status:** Accepted
**Date:** 2026-07-07
**Deciders:** Solo founder

## Context

The real SignalCare EDWP production system is .NET 10 + React 19. The demo could use the same stack for direct parallelism, or a different stack optimized for demo purposes.

Constraints:
- Solo build. Timebox 6-8 weeks. Every day of framework friction is a day not spent on architecture.
- Audience: enterprise architects and AI executive leaders reviewing as portfolio proof-of-work.
- Every mainstream LLM SDK is Python-first. Every mainstream RAG library is Python-first.
- The demo demonstrates the **architecture**, not the language runtime. Cloud-agnostic architecture is language-agnostic.

## Decision

Use **Python 3.12 + FastAPI + Pydantic v2 + asyncio** for the demo backend.

## Consequences

### Positive
- Faster shipping. Every LLM/RAG/OTel binding is one `uv add` away.
- Audience-friendly. FastAPI OpenAPI docs are architect-readable out of the box.
- Cleaner async story. asyncio + BackgroundTask maps directly to the L4 orchestrator pattern.
- Ecosystem alignment with tesseract, docling, pgvector clients, prompt engineering tooling.

### Negative
- Not directly transferable to the production .NET codebase. Architectural patterns transfer; code does not.
- Two languages in the founder's head simultaneously.

### Neutral / Notable
- The architecture is the deliverable, not the code. An enterprise architect reviewing the demo cares about layer separation, adapter interfaces, guardrail enforcement, and observability — none of which is language-specific.

## Alternatives Considered

- **.NET 10 + ASP.NET Core** — same stack as production, but slower to add LLM/RAG bindings; would delay ship dates by 2-3 weeks minimum. Not worth it for a demo.
- **Node.js + NestJS** — similar to Python for LLM tooling but the async story is less clean and there's more boilerplate. Rejected on ergonomics.
- **Go** — great for adapters and runtime, weaker for RAG/LLM stack. Rejected on ecosystem gap.

## References

- Real production stack: `C:\ClaudeAzure\CLAUDE.md`
- Consolidated architecture: `C:\ClaudeAzure\docs\agentic-architecture-consolidated-cloud-agnostic.md`
