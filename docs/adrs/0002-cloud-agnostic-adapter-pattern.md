# ADR-0002 — Cloud-Agnostic via Adapter Pattern with Local Implementations

**Status:** Accepted
**Date:** 2026-07-07
**Deciders:** Solo founder

## Context

The architecture claims cloud-agnostic behavior. This must be provable in the demo, not aspirational. Two failure modes to avoid:

1. **Vendor SDK leak** — using `boto3` or `azure-sdk-*` directly in agent code makes the "cloud-agnostic" claim vaporware.
2. **Adapter theater** — implementing adapters as empty wrappers that just call the vendor SDK doesn't demonstrate portability; it just adds indirection.

## Decision

Every external-platform dependency is expressed as an **abstract base class** in `app/L6_adapters/<capability>/base.py` with concrete implementations in `local.py` (for the demo) and stubs for other providers (`aws.py`, `azure.py`, `gcp.py`) if aspirationally shown.

The demo ships **8 adapters** with real local implementations:

| Adapter | Local Implementation |
|---|---|
| Identity | Keycloak (OIDC) |
| Compute | docker-compose |
| Relational | Postgres 16 + pgvector |
| Object Store | MinIO (S3-compatible) |
| Event Bus | NATS JetStream |
| Secrets | HashiCorp Vault (dev mode) |
| Telemetry | OpenTelemetry → LGTM stack |
| AI Gateway | Ollama + OpenRouter |

**Enforcement rule:** no cloud-vendor SDK imports outside of `app/L6_adapters/`. A repo-level lint check verifies this.

## Consequences

### Positive
- Cloud-agnostic property is auditable via `grep`.
- Local implementations give the demo real (not mocked) infrastructure.
- Migration to any specific cloud is a matter of writing a new concrete implementation of an existing interface.

### Negative
- More code than a direct SDK call.
- Requires discipline to keep adapter interfaces stable as concrete impls diverge.

### Neutral / Notable
- The `boto3` dependency in `pyproject.toml` is confined to `L6_adapters/object_store/local.py` for MinIO's S3-compatibility. A reviewer running `grep -r "boto3" app/` should find hits only in that adapter file.

## Alternatives Considered

- **Direct SDK usage** — simpler but breaks the cloud-agnostic claim. Rejected.
- **Skip Object Store adapter, use raw filesystem** — simpler for demo but doesn't exercise the S3-compatible interface pattern. Rejected — architects want to see this.
- **Use a higher-level abstraction library (dvc/fsspec)** — adds a dependency that itself has to be justified. Rejected — the interface is small enough to hand-roll.

## References

- Architecture: `../ARCHITECTURE.md` § L6 Adapter Contracts
- Consolidated architecture: `C:\ClaudeAzure\docs\agentic-architecture-consolidated-cloud-agnostic.md` § 15
