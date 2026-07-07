# L3 · Specialist Agents

Each agent is a package with:

- `agent.py` — the agent class (`Agent(name, tier, prompt_key, tools)`)
- `tools.py` — tool functions (each wraps a L5 tool)
- `README.md` — purpose, trigger, role served, model tier, guardrails, HITL gate, success metric
- Tests in `tests/L3_agents/<agent_name>/`

## Ships in demo (5 core)

| Agent | Model Tier | Role |
|---|---|---|
| [`compliance_ops/`](compliance_ops/) | Balanced + Fast | **SHIPS FIRST** · Founder Mode digest |
| [`document_extraction/`](document_extraction/) | Reasoning | Extract fields from uploaded docs, create evidence |
| [`provider_intake/`](provider_intake/) | Balanced | Conversational referral intake |
| [`reconciliation/`](reconciliation/) | Balanced | Cross-source conflict detection |
| [`clinical_summary/`](clinical_summary/) | Reasoning | RN-review clinical summary with adversarial verify |

## Stubs (3)

| Agent | Purpose (post-Week-8) |
|---|---|
| [`_stubs/completeness/`](_stubs/completeness/) | Required-field checker |
| [`_stubs/eligibility/`](_stubs/eligibility/) | Eligibility rule + LLM assist |
| [`_stubs/packet_assembly/`](_stubs/packet_assembly/) | AHS submission packet compiler |

## Every Agent Must

- Register in the Agent Registry table on startup
- Have a feature flag `agents.<name>` in `SiteSettings`
- Load its prompt from the Prompt Registry (YAML source of truth + Postgres runtime table)
- Call tools only through the L5 Tool Layer — no direct DB access
- Emit OpenTelemetry spans for every step
- Support the two-agent adversarial verify pattern for high-stakes outputs
