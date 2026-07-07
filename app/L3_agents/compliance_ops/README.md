# Compliance/Ops · Founder Mode Digest

The **first L3 agent** in the demo. Ships first because it exercises every architectural layer without touching PHI — a clean end-to-end proof of the stack before Phase 4's evidence fabric lands.

## Purpose

Every morning at 06:30, produce a terse founder brief that surfaces exactly what needs attention today. Not a status report — an action-forcing digest. See [ADR-0008](../../../docs/adrs/0008-compliance-ops-digest-ux.md) for the UX spec (structure, tone, length ceiling, evidence-only synthesis).

## Trigger

- **Primary:** apscheduler cron, `hour=6, minute=30`, tz from `DIGEST_TZ` env (Prav → America/New_York; default UTC). Lands in Session C.
- **Dev on-demand:** `POST /digest/generate` (env-gated by `ALLOW_ONDEMAND_DIGEST=true`). Also Session C.

## Role served

Prav's founder-mode operating tempo. NOT a compliance report — a founder brief that happens to cover compliance-adjacent topics.

## Model tier

| Tier | Purpose | Session |
|---|---|---|
| **Balanced** (Sonnet via Anthropic) | Digest synthesis | Session B (this one) |
| **Fast** (llama3.2:3b via Ollama) | *Reserved* for pre-processing raw log lines. Not implemented in Session B; ADR-0008 §9 leaves it as a design knob. | Later, only if needed |

## Guardrails

Compliance_ops is a **non-PHI agent**. Requests carry `phi_present=False`. It passes through the L2 stack unchanged — the sentinel and BAA gate observe the request but never block:

- **L2 injection sentinel** — no user content is prompt-shaped, so no detection fires. Present for consistency; every LLM call goes through the same stack.
- **L2 BAA gate** — `phi_present=False` → `decision=allow reason=no_phi` on every call. No block risk.
- **L2 PHI redactor** — scans the input bundle. The bundle contains only structured system metadata (host stats, adapter probes, log counts, hardening JSON) — no natural language with PHI-shaped substrings.

If any of those constraints change (e.g. an incident report gets fed to the digest with real patient data), the agent must be reclassified. Set `phi_present=True` and route through the redactor.

## HITL gate

**None.** The digest is written for Prav to read. There is no downstream action taken automatically. If the digest surfaces something that needs review, the review happens outside this agent (in Slack, in a follow-up session, in an incident ticket).

Compliance_ops is deliberately a **write-once, read-by-human** artifact. Automating on top of it (auto-restart Ollama, auto-page on red) is Phase 5+ scope and requires its own ADR.

## Success metric

- The morning after: Prav can read the digest in under 90 seconds and know what to do first today. Empirically measured by observing whether Prav opens the admin UI `/digest` page within 15 minutes of waking.
- Zero fabricated concerns. Every Attention / Watch / Decisions item must be traceable to a fact in the input bundle. This is the evidence-only constraint from ADR-0008 §6 — if it fails, the prompt gets tightened, not the input trimmed.

## Non-goals for Session B

- **Cron trigger** — apscheduler wiring lands in Session C.
- **Endpoints** — `GET /digest/today` and friends land in Session C.
- **Admin UI page** — `/digest` React page lands in Session C.
- **Email delivery** — deferred to Phase 3+ (needs the L6 comms adapter, not yet scoped).
- **Historical retention policy** — files accumulate in `data/digests/`; pruning is manual until Phase 6+.

## Data sources

Per ADR-0008 §7. All non-PHI.

| Source | Tool | Notes |
|---|---|---|
| Host stats | `psutil` (CPU / memory / disk %) | 1-second CPU sample; disk anchor differs per OS. |
| Ollama health | `GET /api/tags` via `httpx` | Green if 200 + <1000ms, yellow if slow, red on error. |
| Anthropic health | `GET /v1/models` via `httpx` | Green if 200 + <1500ms, yellow if slow, red on error or 401. Yellow if no API key configured. |
| Hardening posture | `data/seed/hardening_status.json` | Seed file with 8 controls; each is compliant / warning / failing. |
| Guardrail activity 24h | Grep of `data/logs/signalcare.log` | Counts BAA denies, PHI redactions by tier, injection blocks + flags. Missing file → all zeros. |

## Persistence

Two artifacts written per generation, both in `data/digests/`:

- `YYYY-MM-DD.json` — raw structured (LLM output + agent-overridden counts + agent-computed systems)
- `YYYY-MM-DD.md` — rendered per ADR-0008 Appendix A/B mockups

Same-day regeneration overwrites (idempotent by filename). `data/digests/` is gitignored — it is grep-able local history, not source of truth.

## Testability

Every dependency is injected via constructor: `AIGateway`, `PromptRegistry`, `PromptRenderer`, and all four data-source paths. Tests substitute a `CapturingGateway`, an in-memory registry, and `tmp_path`-based files; no LLM calls, no live sockets. Adapter probes accept an injected `httpx.AsyncClient` for `MockTransport` in tests.

## Relationship to the L2 guardrails

Compliance_ops is a **consumer** of `app.state.ai_gateway`. It does NOT wrap the gateway. Every L2 guardrail is an `AIGateway` decorator; every L3 agent depends on a wrapped `AIGateway` via `app.state`. See CLAUDE.md architecture discipline for why the L2/L3 distinction matters.

## References

- [ADR-0008 — Digest UX](../../../docs/adrs/0008-compliance-ops-digest-ux.md) — the shape you are implementing.
- [ADR-0009 — Prompt registry](../../../docs/adrs/0009-prompt-registry-yaml-first-postgres-additive.md) — how this agent loads its prompt.
- [ADR-0007 — Injection sentinel](../../../docs/adrs/0007-injection-sentinel.md) — the classifier parser pattern (`_parse_classifier_json`) that `_parse_digest_json` mirrors.
- [`../README.md`](../README.md) — L3 agent conventions (registry entry, feature flag, prompt registry usage, OTEL spans).
