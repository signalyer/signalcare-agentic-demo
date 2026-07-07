# L6 · Cloud-Agnostic Platform Adapters

Eight adapter interfaces. Each has:

- `base.py` — abstract interface (docstrings mandatory)
- `local.py` — the demo concrete implementation
- Optional: `aws.py`, `azure.py`, `gcp.py` — stubs for aspirational providers

## Enforcement Rule

**No cloud-vendor SDK imports outside this folder.** A repo-level lint check enforces this — `boto3`, `azure-*`, `google-cloud-*` may only appear in files under `app/L6_adapters/`.

## Adapters

| Folder | Contract | Demo Implementation |
|---|---|---|
| [`identity/`](identity/) | AuthN, AuthZ, groups, service accounts | Keycloak (OIDC) |
| [`compute/`](compute/) | Long-running services, workers, jobs | docker-compose |
| [`relational/`](relational/) | ACID transactions, schemas, pgvector | Postgres 16 |
| [`object_store/`](object_store/) | Immutable blob storage with versioning | MinIO (S3-compatible) |
| [`event_bus/`](event_bus/) | Pub-sub, queues, streams | NATS JetStream |
| [`secrets/`](secrets/) | Secrets storage + rotation | HashiCorp Vault (dev mode) |
| [`telemetry/`](telemetry/) | Logs, metrics, traces via OTLP | OpenTelemetry → LGTM |
| [`ai_gateway/`](ai_gateway/) | Model routing by tier, BAA-gated egress | Ollama + OpenRouter |
