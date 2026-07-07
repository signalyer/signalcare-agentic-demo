# ADR-0003 — Defer Container Runtime (Docker Compose Stack) to Phase 3

**Status:** Accepted
**Date:** 2026-07-07
**Deciders:** Solo founder

## Context

The scaffold session (Phase 0, 2026-07-07) authored a `docker-compose.yml` with the full 8-adapter local stack: Postgres+pgvector, MinIO, NATS JetStream, Vault, Keycloak, Ollama, and the LGTM observability stack (Grafana + Loki + Tempo + Prometheus). Phase 1 (Week 1) Definition of Done, per `TASKS.md`, includes "all docker services healthy" and "Grafana dashboard #1."

On session start for Phase 1, the target development machine had no container runtime installed (no Docker Desktop, no Podman, no Docker CE in WSL). WSL2 Ubuntu is present but stopped.

Forces:

- **Real Ollama + real OpenRouter are what Week 1's `/agents/echo` DoD actually exercises.** Nothing else in the docker-compose stack is on the Week 1 code path — Postgres/NATS/MinIO/Vault/Keycloak first become load-bearing in Phase 2 or later, and the other three Grafana dashboards land in Phase 3.
- **Container-runtime install has real cost** — Docker Desktop requires admin, ~500MB, and a restart; Docker CE in WSL2 requires ~20 min of manual setup and every dev command runs inside a WSL shell.
- **The cloud-agnostic claim in ADR-0002 is about the adapter interface, not the container substrate.** Whether Ollama runs in a container or as a Windows service, `L6_adapters/ai_gateway/local.py` calls the same `http://…:11434/api/chat` endpoint. The abstraction is unchanged.
- **Delaying productive Week 1 coding to install container tooling would burn ~2 hours of a 40-hour week** for no architectural gain.

## Decision

Defer bring-up of the docker-compose stack from **Phase 1 (Week 1)** to **Phase 3 (Week 3)**, where Postgres, NATS, Vault, and the LGTM observability stack all first become load-bearing anyway.

Concretely for Week 1:

- **Install Ollama natively on Windows** (via `winget install Ollama.Ollama` or the ollama.com installer). Ollama runs as a background service on `http://localhost:11434`.
- **Set `OLLAMA_HOST=http://localhost:11434`** in `.env` (overriding the docker-compose-service-name default of `http://ollama:11434`).
- **Move `Grafana dashboard #1` (request rate, latency, model breakdown) from Phase 1 to Phase 3.** The other three dashboards already land in Phase 3 — batching them is more coherent than delivering a one-off in Phase 1.
- **The AI Gateway adapter (`base.py` + `local.py` + `openrouter.py` + `router.py`) and the `/agents/echo` endpoint remain Phase 1 deliverables.** These are the actual architectural proof-points from ADR-0002.

Container runtime install decision (Docker Desktop vs Docker CE in WSL2) is deferred to the Phase 3 kickoff. At that point we know which stack services we actually need running and can choose accordingly.

## Consequences

### Positive

- Phase 1 code delivery unblocked on session start; no install/admin friction.
- Real Ollama + real OpenRouter still exercised — the adapter abstraction gets tested against two genuinely different providers this week, which is the actual claim from ADR-0002.
- Grafana dashboards ship as a coherent set of four in Phase 3, not one-then-three.
- Container-runtime decision (Desktop vs WSL CE) can be informed by two weeks of hands-on with the codebase rather than made upfront under pressure.

### Negative

- The Week 1 DoD becomes weaker in an obvious way: no telemetry dashboard proving the two provider calls happened. Mitigation: log adapter calls with `structlog` and stdout-print latency + token counts, so the terminal is the interim dashboard.
- Anyone else cloning the repo before Phase 3 will hit a broken `make status` — the Makefile assumes `docker compose ps` works. Mitigation: add a `make status-lite` target that pings native Ollama + hits OpenRouter's health endpoint.
- The scaffold's `docker-compose.yml` sits unused for two weeks. Not a bug, but reviewers may ask why it exists without being run. Answer: it's the Phase 3 deliverable, pre-authored.

### Neutral / Notable

- **This ADR does not deprecate the docker-compose approach.** The compose file remains the source-of-truth for how services are wired together, and Phase 3 will bring it up. This is a phasing decision, not a substrate change.
- **The `.env` file's docker-service-name defaults (`http://ollama:11434`, `http://postgres:5432/...`) will need to be overridden per-machine during Weeks 1-2.** Document this in `README.md` under "Local dev without containers."

## Alternatives Considered

- **Install Docker Desktop immediately.** Rejected on time cost (~10 min install + restart + WSL2 integration + license check) vs zero architectural gain for Week 1's actual code path.
- **Install Docker CE inside WSL2 Ubuntu.** Rejected for Week 1 on friction cost (docker daemon doesn't auto-start; every `docker compose` command runs inside a WSL shell). Remains a viable Phase 3 option.
- **Native install of every service (Postgres, NATS, Vault, Keycloak, LGTM).** Rejected — massive setup cost, Windows-native builds vary in quality (especially Keycloak), and it would erode the reproducibility claim in the README without a matching benefit.
- **Write adapter code with mocks only, no real Ollama.** Rejected — the "working code beats clever abstractions" persona in project CLAUDE.md means Week 1 wants a real end-to-end call through both providers. Mocks would prove the interface parses; they wouldn't prove the abstraction holds under a real provider quirk.

## References

- ADR-0002 (Cloud-Agnostic Adapter Pattern) — this ADR is a phasing refinement, not a change to the substrate contract
- `TASKS.md` § Phase 1 (Week 1) — items re-annotated to reflect the deferral
- `docs/handoffs/2026-07-07-scaffold-to-week1.md` — the handoff document being executed against
