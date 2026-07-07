# ADR-0009 — Prompt Registry: YAML-First for Phase 2, Postgres Additive in Phase 3

**Status:** Accepted
**Date:** 2026-07-07
**Deciders:** Solo founder

## Context

Build-plan lines 30-31 name two artifacts for the Compliance/Ops delivery:

    - Prompt in `app/L0_observability/prompts/compliance_ops_digest.yaml`
    - Prompt registry table + on-startup sync from YAML

`CLAUDE.md` non-negotiable rule 6 elevates this to the whole project:

    6. Prompt registry has both YAML source of truth and Postgres runtime table.
       Both must be updated together.

ADR-0003 defers the docker/Postgres stack to Phase 3. That deferral is the reason Phase 2 code paths still work — Ollama runs native, Anthropic is called direct — but it collides directly with rule 6. Phase 2 needs to ship a prompt registry, and it must not depend on infrastructure that has not been provisioned yet.

The handoff (`docs/handoffs/2026-07-07-phase2-tasks-1-2-to-injection-sentinel.md`, question 3) surfaced three options:

- (i) YAML-only, defer Postgres sync to Phase 3
- (ii) SQLite as a Phase 2 stand-in
- (iii) In-memory dict seeded from YAML at startup

Handoff recommended (i). This ADR resolves how to do (i) *without* silently discarding rule 6 — the rule's spirit (durable audit trail; "which prompt served this call") has to hold from day one.

Six sub-questions:

1. **Storage substrate for Phase 2 and Phase 3.**
2. **YAML file location and per-file naming.**
3. **YAML schema — the fields every prompt entry must expose.**
4. **Versioning scheme — how a "prompt version" is identified.**
5. **Startup semantics — how the registry loads, how drift from prior startups is surfaced.**
6. **Access pattern — how agents obtain a prompt at call time.**

## Decision

**1. Storage — interface-first. Two implementations across phases.** Define a `PromptRegistry` protocol that agents depend on. Ship two implementations:

- **Phase 2 (now):** `FileBackedPromptRegistry` — reads YAML files from `app/L0_observability/prompts/`, writes a startup snapshot to `data/prompt_registry_state.json`. No database dependency.
- **Phase 3 (with the compute adapter):** `PostgresPromptRegistry` — same interface; upserts YAML entries into a Postgres table at startup; writes runtime records for every call served. Restores strict rule-6 compliance.

Agents talk to the `PromptRegistry` protocol, not to either concrete implementation. Swapping happens in `main.py` lifespan; no agent code changes. This is the same L6-adapter shape ADR-0002 established: interface first, adapters swap without callers noticing.

Rule 6 is temporarily relaxed for Phase 2. The relaxation is time-boxed: PostgresPromptRegistry is a Phase 3 deliverable, and Phase 3 restores the full rule. The relaxation is documented HERE so a reviewer never has to guess whether rule 6 was ignored or acknowledged.

**2. File location and naming.**

- Directory: `app/L0_observability/prompts/`
- One file per prompt.
- File name = prompt key = `<agent_name>_<purpose>.yaml`. Examples: `compliance_ops_digest.yaml`, `document_extraction_field.yaml`, `injection_sentinel_classifier.yaml`.
- The prompt key is the YAML filename minus the extension. Agents call `registry.get("compliance_ops_digest")`.

Colocation of prompts under `L0_observability/` (not under each agent's package) is deliberate: prompts are observability + governance concerns, not implementation details of a single agent. The prompt registry browser (build-plan line 128) lists everything from this one directory.

**3. YAML schema.** Every prompt file MUST have all the fields below. Missing required fields → registry startup fails loudly.

```yaml
# Required — identity and description
id: compliance_ops_digest                    # must match filename minus extension
description: >-
  Founder Mode daily digest. Reads a bundle of non-PHI evidence
  (host stats, adapter health, hardening, guardrail 24h counts) and
  produces a fixed-5-section brief per ADR-0008.
owner: prav                                  # who to ask when this needs revision

# Required — model routing
tier: balanced                               # fast | balanced | reasoning (Tier enum values)
max_tokens: 1200
temperature: 0.2

# Required — content
system: >-
  You are a senior operations analyst producing a daily brief for a founder.
  Terse. Imperative. Action-forcing. No emojis, no hedging.
user_template: |-
  Today's evidence bundle. Only report facts present below. Do not speculate.

  Host stats: {host_stats}
  Adapter health: {adapter_health}
  Hardening: {hardening_status}
  Guardrail activity (last 24h): {guardrail_activity_24h}

  Return ONLY valid JSON matching this exact schema:
  {output_schema_inline}

  No preamble. No markdown. No extra keys.

# Required — placeholder validation. Names must exactly match {…} in user_template.
placeholders:
  - host_stats
  - adapter_health
  - hardening_status
  - guardrail_activity_24h
  - output_schema_inline

# Required — JSON schema the caller expects back (per CLAUDE.md rule "schema in prompt").
# Embedded into user_template via {output_schema_inline}.
output_schema:
  type: object
  properties:
    date: {type: string}
    attention: {type: array, maxItems: 3}
    watch: {type: array, maxItems: 3}
    guardrails: {type: object}
    systems: {type: array}
    decisions: {type: array, maxItems: 3}
  required: [date, attention, watch, guardrails, systems, decisions]

# Required — provenance
created_at: '2026-07-14'                     # date the prompt was first added
notes: |-
  Companion to ADR-0008. Do not add sections without editing that ADR.
  Do not remove the schema-in-prompt block — CLAUDE.md rule.
```

Fields are stable across Phase 2 and Phase 3; the Postgres runtime table's columns will mirror them 1:1.

**4. Versioning — content hash.** The version identifier is `sha256(yaml_file_bytes)`, first 12 hex chars. Computed at registry load time. Every logged Claude API call carries `prompt_hash=X`. Two consequences:

- "Which prompt served this call" is provable from log lines alone — no Postgres required for that answer.
- Phase 3 Postgres history table is *additive*: the version identifier is stable across substrates, so Phase 3 can retroactively backfill entries from log grep without a data migration.

Semver (`v1.2.0`) was considered and rejected — see Alternatives. YAML files never carry a `version:` field; the version emerges from content.

**5. Startup semantics — load, snapshot, log drift.** On startup:

1. Walk `app/L0_observability/prompts/*.yaml`.
2. Parse each. Validate the schema (required fields present, placeholders in `placeholders:` match `{…}` in `user_template`, `tier` is a valid `Tier` value).
3. Compute content hash.
4. Load into memory as `PromptDefinition` dataclasses.
5. Compare each prompt's hash against the previous snapshot in `data/prompt_registry_state.json` (if present).
6. Log INFO for every prompt loaded (`prompt_registry_loaded key=X hash=Y`); log WARN for every hash change since the prior snapshot (`prompt_drift key=X old_hash=Y new_hash=Z`).
7. Overwrite `data/prompt_registry_state.json` with the current snapshot: `{prompt_key, prompt_hash, source_file, loaded_at}` per entry.

Startup fails loudly on any schema violation. A registry that silently drops a broken prompt is worse than one that refuses to start — the agent that expects the prompt will fail later with a less helpful message.

The state file is not committed to git (`.gitignore` picks it up). Git already tracks the YAML source of truth; the state file is a runtime artifact whose only reader is the next startup's drift comparator.

**6. Access pattern — singleton in `app.state`, direct `.get(key)`.**

    # In lifespan:
    app.state.prompt_registry = FileBackedPromptRegistry(
        prompts_dir=Path("app/L0_observability/prompts"),
        state_file=Path("data/prompt_registry_state.json"),
    )

    # In an agent:
    definition = request.app.state.prompt_registry.get("compliance_ops_digest")
    system, user = renderer.render(definition, host_stats=..., ...)

The renderer is a separate concern (not part of the registry itself): given a `PromptDefinition` and placeholder values, it validates that every placeholder is provided, inlines the `output_schema` into `{output_schema_inline}`, and returns `(system, user)` strings ready to hand to the AI gateway. Renderer misuse (missing placeholder, unexpected placeholder) raises `PromptRenderError` — loud, not silent.

Hot-reload is NOT supported in Phase 2. YAML changes require a restart. This is a deliberate simplification — production hot-reload use cases (A/B prompt experiments, in-flight tuning) land in Phase 3+ alongside the Postgres store.

## Consequences

### Positive

- **Rule 6's spirit is preserved from day one.** "Which prompt served this call" is provable via `prompt_hash` in log lines even in Phase 2. Rule 6's letter is restored in Phase 3. The relaxation is documented and time-boxed, not silent.
- **No new dependency for Phase 2.** SQLite would have added `sqlite3` as a Python-stdlib zero-op but also a schema migration story when Postgres lands. YAML + JSON snapshot avoid the migration entirely.
- **Phase 3 delivery is purely additive.** `PostgresPromptRegistry` implements the same interface; wiring change in `main.py` is a single line; no agent code touches. The state file becomes vestigial (can be deleted).
- **Content-hash versioning is substrate-agnostic.** Same version identifier in file-backed, Postgres-backed, or a future gRPC-backed registry. Never do a "migrate versions" pass.
- **Startup drift log gives a manual git-alternative audit trail.** Every prompt change since the last startup is a WARN line with old_hash → new_hash. In Phase 2 that IS the audit history.
- **Interface-first matches the ADR-0002 shape.** Consistent architectural pattern reduces cognitive load for someone reading the codebase across L2/L3/L6 — everything is an interface with pluggable implementations.

### Negative

- **Rule 6's literal reading is violated in Phase 2.** Any reviewer reading `CLAUDE.md` today sees a rule; running the Phase 2 code shows no Postgres. This ADR is the reconciliation, but it depends on the reviewer finding it. Mitigated by cross-linking rule 6 to this ADR (see References below); a follow-on documentation patch could add an inline pointer next to rule 6.
- **No historical prompt versions in Phase 2.** Restart-after-YAML-edit loses the prior version's snapshot. Git preserves the file text, but the registry does not remember it ran with a prior hash yesterday. This is the audit trail Phase 3 restores.
- **No hot-reload.** Prompt tuning requires restart. A minor development friction; acceptable for Phase 2 solo iteration.
- **The renderer being a separate concern is a small extra file.** Registry doesn't render; renderer takes a definition. Split is worth it because rendering is where placeholder validation happens, and validation logic away from storage keeps both testable in isolation.

### Neutral / Notable

- **`data/prompt_registry_state.json` is a small runtime artifact** — one line per prompt. Tens of prompts, sub-kilobyte per startup. No rotation needed.
- **The gitignore of the state file is a decision worth revisiting** if a future incident requires "what did we load 3 days ago." Git-tracked snapshot is one line of `.gitignore` from happening; do not enable until the audit case is real.
- **The `notes:` field is free-form and expected to point at the ADR that governs the prompt.** A tightly-controlled prompt (compliance_ops_digest → ADR-0008) has a note saying so. A prompt without a governing ADR is a smell.
- **The `owner:` field is a human name, not a role.** Small team; direct accountability is more useful than an abstract role today.

## Alternatives Considered

- **(ii from handoff) SQLite as a Phase 2 stand-in.** Rejected. Adds a schema-migration story when Postgres lands; buys marginally more than the JSON state file (which already provides the audit-trail signal Rule 6 cares about); adds a substrate that must be reasoned about in tests. Cost > benefit.
- **(iii from handoff) In-memory dict seeded from YAML, no snapshot file.** Rejected. Loses the drift-detection audit signal on every restart. The dict shape is fine at runtime; the shape at *startup* is what we care about, and no persistence means no audit.
- **YAML-only with no snapshot, no drift log, no version hash.** Rejected. Reduces to (iii). Silently drops rule 6's spirit as well as its letter.
- **Full VersionedRegistry with append-only history in Phase 2.** Rejected. Speculative abstraction. Phase 3 delivers this correctly on top of Postgres; building it now on top of files is a stall.
- **Semantic version (`v1.2.0`) instead of content hash.** Rejected. Requires human discipline to bump on every edit (people forget); introduces a "did the version get bumped for this change" review overhead; produces the same audit signal (a change identifier) that content-hash produces automatically. Semantic version is useful when the versioning conveys *intent* (breaking vs. compatible); prompt edits do not have that structure.
- **YAML at each agent's package (`app/L3_agents/compliance_ops/prompt.yaml`)** instead of centralized `L0_observability/prompts/`. Rejected. Prompts are governance artifacts (compliance auditors read them, versioning matters, drift matters); scattering them under agent packages fights the Phase 8 prompt registry browser deliverable and the drift-log observability path.
- **Wait for Phase 3 Postgres to land, delay Compliance/Ops.** Rejected. That inverts ADR-0003 and slides the L2 proof-point. Compliance/Ops is deliberately the first agent shipped precisely because it's non-PHI and hits every layer; delaying it delays the whole Week 2 goal.
- **Rule 6 rewrite to make Postgres explicitly optional.** Rejected as a stand-alone move — rule 6 will be restored to full strength when Phase 3 lands, so weakening its wording now would either need re-tightening later or leave the project with a permanently weaker guarantee. This ADR relaxes rule 6 in a *time-boxed* way, which is a different act than editing the rule itself.

## References

- `docs/build-plan.md` lines 30-31 — YAML source + Postgres runtime sync, the target end-state this ADR delivers in two phases.
- `docs/build-plan.md` line 128 — Phase 8 Prompt Registry Browser, which reads from the same interface either implementation exposes.
- `CLAUDE.md` non-negotiable rule 6 — the rule this ADR temporarily relaxes and pins to Phase 3 for restoration. **Any reader auditing rule 6 compliance MUST read this ADR.**
- ADR-0002 (cloud-agnostic adapter pattern) — the interface-first shape this ADR reuses at the registry layer.
- ADR-0003 (defer container runtime to Phase 3) — the cause of the rule-6 collision this ADR resolves.
- ADR-0008 (compliance-ops digest UX) — the first consumer of the registry; its prompt schema is what the initial YAML file will encode.
- `CLAUDE.md` prompt-JSON-schema rule — the `output_schema` YAML field and its inlining into `user_template` via `{output_schema_inline}` is where this rule lives durably.
- `app/L3_agents/README.md` — "Load its prompt from the Prompt Registry (YAML source of truth + Postgres runtime table)" — every agent's contract with the registry.
- Follow-on: `app/L0_observability/prompt_registry/` package (build-plan Phase 3 line 70) is where `PostgresPromptRegistry` lands. The Phase 2 `FileBackedPromptRegistry` lives in the same package to avoid a Phase 3 rename.
