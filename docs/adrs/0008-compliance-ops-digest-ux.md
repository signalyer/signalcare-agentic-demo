# ADR-0008 — Compliance/Ops (Founder Mode) Digest — UX Specification

**Status:** Accepted
**Date:** 2026-07-07
**Deciders:** Solo founder

## Context

Build-plan line 28 names the third Phase 2 deliverable — `app/L3_agents/compliance_ops/`, the Founder Mode digest agent. Build-plan line 32 pins the trigger: apscheduler cron at 06:30 local, plus a `/digest/today` endpoint. Line 22 sets the boundary: **non-PHI agent**. Compliance-ops is deliberately the first agent shipped precisely because it does not touch patient data — it exercises the L2 stack, the L4 orchestrator hooks, the prompt registry, and the L5 tool layer without needing the L2B evidence fabric to land first.

The handoff from the prior session (`docs/handoffs/2026-07-07-phase2-tasks-1-2-to-injection-sentinel.md`, question 2) called out digest UX design as a **hard blocker** on writing the agent prompt:

> Digest UX design — the Compliance/Ops (Founder Mode) agent produces a daily 06:30 digest per build-plan line 32. WHAT does the digest LOOK like before we write the agent? Sections? Length? Tone? Distribution channel? Design a mockup or written spec BEFORE writing the LLM prompt.

Reason for the block: an LLM-generated status brief has three canonical failure modes — (1) marketing-prose drift, (2) hallucinated concerns fabricated from thin data, (3) unbounded length. All three are shape-of-the-prompt problems. Deciding "what shape do we want" before writing the prompt is cheaper than iterating on a bad output.

Five sub-questions this ADR resolves:

1. **Audience and purpose.** Who reads this? What decision are they making?
2. **Distribution channel.** File? Admin UI? Email? Slack? Multiple?
3. **Structure.** Fixed sections vs. free-form narrative.
4. **Length + tone.** Word ceiling. Voice discipline.
5. **Data-in / data-out shape.** JSON schema for the LLM's output. Which parts are LLM-synthesized vs. computed and inserted.

## Decision

**1. Audience and purpose — Prav specifically; "what needs me today" not "what happened yesterday".** Founder Mode (per Paul Graham's essay) is action-forcing, not status-reporting. The digest is the first thing read at 06:30 and it must earn its 90-second read by surfacing exactly what would otherwise sit in Slack DMs, monitoring dashboards, and audit logs. If a section has nothing decision-relevant, it says so — it does not fabricate content to look thorough.

**2. Distribution — admin UI page + on-disk file. Email deferred to Phase 3.**

Two artifacts written per generation:

- `data/digests/YYYY-MM-DD.md` — rendered markdown, human-readable, grep-able
- `data/digests/YYYY-MM-DD.json` — raw structured (the LLM's JSON output plus computed counts)

Two HTTP surfaces:

- `GET /digest/today` — returns the latest generated JSON (from file, not on-the-fly)
- `GET /digest/{YYYY-MM-DD}` — returns a specific historical digest JSON

One admin UI page:

- `/digest` — renders the latest markdown from `data/digests/*.md`, with a date picker to browse history

One developer surface (gated by env `ALLOW_ONDEMAND_DIGEST=true`, default false):

- `POST /digest/generate` — regenerates today's digest immediately. For demos and manual triggers; not a production interface.

Email is out of scope for Phase 2 — it requires an L6 communications adapter that is not scheduled until Phase 3. Slack is not on the roadmap. If Prav wants push notification before Phase 3 lands, the admin UI page will do — 06:30 is close enough to the workday that "open the tab" is a viable habit.

**3. Structure — FIXED five sections, fixed order, always all five headers present.** Empty sections print `None.` explicitly. This makes the digest visually predictable across days and prevents the LLM from padding sparse days with fluff.

    ## Attention
    ## Watch
    ## Guardrails
    ## Systems
    ## Decisions I need

- **Attention** — 0-3 items requiring action today. Each is one headline + one evidence line.
- **Watch** — 0-3 items trending in a bad direction; may need action in 24-72h.
- **Guardrails** — computed counts from the last 24h of L2 log lines. NOT LLM-generated.
- **Systems** — subsystem health (host, adapters, hardening controls). Data-driven; LLM produces the note line only.
- **Decisions I need** — 0-3 open questions blocking downstream work. Each is one question + one context line.

The 3-item cap on Attention / Watch / Decisions is deliberate. A digest with 8 attention items has no attention — Prav will skim and act on none. Forcing the LLM to rank and cut is the point.

**4. Length and tone.**

- **Body budget:** 300 words maximum across all five sections combined. Enforced at generation via `max_tokens=1200` (rough 4:1 token-to-word ratio + JSON structure overhead).
- **Voice:** imperative, active. "Ollama unreachable since 03:12. Restart or fail-open?" — not "The Ollama service appears to be experiencing connectivity issues."
- **Ban list:** no emojis. No hedging ("appears to", "may indicate", "seems to"). No marketing language ("robust", "seamlessly", "leverage"). No unsolicited recommendations that were not requested. No apology preambles ("Unfortunately," etc.).
- **Item shape:** every Attention / Watch item = one-sentence headline + one-sentence evidence citation. Every Decisions item = one-sentence question + one-sentence context.

**5. Data model — JSON schema (LLM output).** The agent's Balanced-tier call produces THIS schema; the renderer converts it to markdown. Counts under `guardrails` are computed by the tool layer BEFORE the LLM call — the LLM never does arithmetic on log counts (LLMs miscount, especially at low temperature). The LLM synthesizes Attention / Watch / Decisions from the raw evidence bundle it is handed, and produces the free-text `note` fields under `systems`. Everything else is passed through unchanged.

```json
{
  "date": "YYYY-MM-DD",
  "generated_at": "ISO-8601 UTC",
  "attention": [
    {"headline": "string, max 90 chars, imperative voice",
     "evidence": "string, max 140 chars, one fact + source"}
  ],
  "watch": [
    {"headline": "string, max 90 chars",
     "evidence": "string, max 140 chars, one fact + source"}
  ],
  "guardrails": {
    "phi_redactions": {"total": 0, "T1": 0, "T2": 0, "T3": 0},
    "baa_blocks": 0,
    "injection_blocks": 0,
    "injection_flags": 0
  },
  "systems": [
    {"name": "string (e.g. ollama, anthropic, host_cpu, host_disk, hardening)",
     "state": "green|yellow|red",
     "note": "string, max 100 chars, null if state is green and unremarkable"}
  ],
  "decisions": [
    {"question": "string, max 100 chars, one sentence",
     "context": "string, max 140 chars, why this blocks progress"}
  ]
}
```

Section counts (`attention.length`, `watch.length`, `decisions.length`) are each capped at 3. If the LLM returns more, the renderer takes the first 3 and logs a WARN — this is a policy violation the LLM prompt discourages, not a rendering feature.

**6. Evidence-only constraint.** The LLM synthesis prompt states, in this exact shape: *"You may only report facts present in the input data below. Do not speculate. Do not extrapolate. If the input contains no decision-relevant material, return empty arrays for `attention`, `watch`, and `decisions`."* This is the primary defense against hallucinated concerns — a documented LLM failure mode where a status-report prompt with sparse input causes the model to invent plausible-sounding issues to fill the shape.

**7. Data sources (Phase 2).** All non-PHI.

- **Host stats via `psutil`** — CPU 1min avg, memory %, disk %. Feeds `systems`.
- **Adapter health probes** — Ollama `GET /api/tags`, Anthropic `HEAD /v1/messages` (or a cheap `GET /v1/models` equivalent). Feeds `systems`.
- **`data/seed/hardening_status.json`** — seed file of hardening controls (BAA gate on, redactor mode, sentinel mode, feature-flag posture). Feeds `systems`.
- **L2 guardrail log parse** — grep the last 24h of `signalcare.baa_gate`, `signalcare.phi_redactor`, `signalcare.injection_sentinel` structured log lines. Feeds `guardrails` counts.

Postgres audit table is deferred (docker stack out of scope per ADR-0003); when it lands in Phase 3, it becomes an additive source for `guardrails` without changing the schema.

Sources sent to the LLM are labeled and bounded: the raw evidence bundle is a JSON blob under 4KB with named sections (`host_stats`, `adapter_health`, `hardening_status`, `guardrail_activity_24h`). The LLM sees data, not raw log lines.

**8. Trigger and persistence.**

- **Cron:** apscheduler cron trigger, `hour=6, minute=30`, timezone = `America/New_York` (Prav's TZ; source of truth in a `DIGEST_TZ` env var, default `UTC` when unset).
- **On generation:** write BOTH `.json` and `.md` to `data/digests/`. Idempotent by filename — same-day regeneration overwrites (that is the intended behavior for the dev on-demand endpoint).
- **Retention:** no automatic cleanup. `data/digests/` accumulates until Prav prunes. Phase 3+ can add rotation.
- **`/digest/today`:** reads the file named `YYYY-MM-DD.json` for today's local date. If the file does not exist yet (before 06:30 first run, or on a fresh install), returns HTTP 404 with `{"error": "no digest generated yet today"}` — not a stale digest, not an empty one.

**9. Tier composition — Balanced-only for synthesis; Fast reserved for a potential pre-processing stage.** The L3 README lists compliance_ops as "Balanced + Fast". The Balanced call is the digest synthesis. The Fast call, if it exists, is for pre-processing raw log lines into bucketed evidence before Balanced synthesizes. Decision deferred to implementation: if a raw-log-to-bucket step benefits from LLM classification (novel log formats, ambiguous severity), add the Fast call; if regex parsing suffices, drop it. This ADR does not require the Fast call — it names it as an available knob.

**10. Prompt registry entry.** The digest prompt is stored at `app/L0_observability/prompts/compliance_ops_digest.yaml` per build-plan line 30, versioned, and loaded by the agent through the prompt registry. The version pin is set at agent-registration time. The prompt file will contain the sections-and-schema instruction block from section (5) verbatim — the schema IS in the prompt, per `CLAUDE.md` JSON-schema rule.

## Consequences

### Positive

- **Terse, predictable structure keeps the digest scan-time under 90 seconds.** The 300-word ceiling and fixed 5 sections make Prav's read pattern the same every day — muscle-memory eye path, no drift.
- **Empty sections stay empty.** The evidence-only constraint + explicit `None.` rendering defeats the "invent something to fill the space" failure mode. A quiet day looks quiet, which is signal.
- **Guardrail counts are computed, not generated.** LLMs miscount. Removing arithmetic from the model's output lifts a class of subtle wrong-number bugs.
- **File-first persistence needs no database.** `data/digests/*.md` is grep-able history from day one. Phase 3's Postgres audit table becomes an additive replacement, not a required prerequisite.
- **Deferring email keeps Phase 2 scope tight.** The L6 comms adapter is one deliverable; email templates + retry + rate-limiting is another. Both are Phase 3+ work; forcing them into Phase 2 delays the whole guardrail proof-point.
- **The JSON output shape survives the future.** New data sources (Postgres audit, cost telemetry, incident logs) show up as additive input to synthesis or additive fields under `guardrails` / `systems`. Sections stay stable.

### Negative

- **No push notification means Prav must open the URL.** If he skips a day, the digest sits unread. Mitigated by cron log entries (someone monitoring can grep for missed reads); worst-case mitigated by Phase 3 email delivery.
- **300-word ceiling can be too tight in a genuinely bad day.** Example: three unrelated Attention items plus two Watch plus two Decisions may not fit in one-sentence-each. Mitigated by evidence-only constraint — if there is more to say, the raw JSON has it, and the admin UI can offer an expandable "raw evidence" pane later. The digest itself stays terse.
- **Fixed sections risk missing a novel issue class.** Something that is neither a system, guardrail, decision, nor rankable in Attention/Watch. Mitigated by treating anything genuinely novel as an Attention item — the section boundaries are broad enough to cover most surprises.
- **The evidence-only constraint may frustrate the LLM into generating uselessly-cautious output.** Balanced tier (Sonnet) is empirically OK with this shape; if the first calibration pass produces a lot of "insufficient data" empties on days that clearly have signal, tune the prompt with more explicit examples of what counts as evidence-worthy.

### Neutral / Notable

- **The "Balanced + Fast" tier split is preserved as a design knob**, not a mandate. First implementation pass ships Balanced-only; add Fast pre-processing if a specific data source needs it.
- **`DIGEST_TZ=America/New_York`** is a Prav-specific default. If a future collaborator lives elsewhere, they set their own value. The env is the seam.
- **Retention policy is intentionally absent.** Storage is measured in kilobytes/day. Prunning becomes a real concern at hundreds of days; it can wait.
- **The renderer is stupid on purpose.** Given a well-formed JSON, produce well-formed markdown. Any complex logic (severity coloring, trend arrows) is out of scope — the digest is text-first, not a mini-dashboard.
- **The digest is not a compliance report.** It is a founder brief that happens to cover compliance-adjacent topics. HIPAA reports, SOC2 evidence packets, and internal audit letters are separate artifacts with different audiences.

## Alternatives Considered

- **Free-form LLM narrative (no fixed sections).** Rejected. Drift into marketing prose is the single most common failure mode for "brief" prompts. Fixed sections are a hard constraint the LLM cannot argue with.
- **Slack post as primary channel.** Rejected. External service dependency, PHI-adjacent review overhead for enterprise buyers, and the L6 comms adapter is not scoped for Phase 2. Slack could be an additive later delivery.
- **Email now (Phase 2).** Rejected. L6 comms adapter is Phase 3+ scope; forcing it into Phase 2 slows the whole L2 proof-point delivery.
- **LLM computes guardrail counts from raw log lines.** Rejected. LLMs miscount, especially with structured input where the "obvious" answer is a small integer and the model gets close but not exact. Compute the count in code, insert it into the prompt as an already-answered fact, and prompt the LLM only for synthesis over facts.
- **Multiple digests per day (morning + evening).** Rejected for Phase 2. Doubles cron infrastructure and evening data is inherently less actionable than morning ("it happened after hours, decide tomorrow"). Phase 6+ could add evening-of-day-N summarization for weekly review.
- **A general-purpose "Notes" free-text section.** Rejected. Opens the door to the exact LLM-rambling failure the fixed-section design prevents. If a novel issue class emerges, it becomes an Attention or Watch item.
- **JSON-only output, no markdown rendering.** Rejected. The admin UI page and the file artifact both benefit from human-readable format; renderer overhead is trivial; JSON is preserved alongside as the machine-readable source.
- **Retention policy at generation time (rotate after N days).** Deferred. Storage cost is negligible; complexity of "did I mean to delete that" outweighs disk savings today. Phase 6+ can add if measured storage growth warrants it.

## References

- `docs/build-plan.md` lines 20-36 — Week 2 Compliance/Ops deliverables, cron 06:30, `/digest/today` endpoint, `make demo-digest` DoD.
- `docs/handoffs/2026-07-07-phase2-tasks-1-2-to-injection-sentinel.md` question 2 — the design-before-prompt block this ADR resolves.
- ADR-0005 (BAA gate) and ADR-0007 (injection sentinel) — canonical log line shapes the guardrail-count parser reads.
- ADR-0006 (redactor tier taxonomy) — `phi_redactions.T1/T2/T3` field names align with the redactor's tier vocabulary.
- `app/L3_agents/README.md` — every agent must load its prompt from the prompt registry, register in the Agent Registry table, emit OTEL spans. Compliance-ops follows the shape verbatim.
- `CLAUDE.md` prompt-JSON-schema rule — the digest prompt MUST include the schema block from decision (5) inline.
- `CLAUDE.md` non-negotiable rule 3 — the digest itself is an LLM call; it passes through the L2 stack. The digest generation call carries `phi_present=False` (non-PHI agent by design); if that ever changes, wire it as a positive-phi request that flows through the redactor.
- Follow-on: prompt registry (build-plan line 31) will hold the digest prompt as its first canonical entry — the ADR is a prompt content spec.

## Appendix A — Rendered Mockup: A day with signal

The digest for a plausible Phase-3-era day where multiple things need attention. Illustrates the fixed structure, the tone, the length ceiling, and the empty-section handling by exercising the `decisions` section as a partial (1 item, not 3).

    # SignalCare Ops Digest — 2026-08-14

    ## Attention

    - **Ollama unreachable since 03:12; injection sentinel degraded to regex-only.**
      Fail-open logged 47 sentinel-classifier-error lines overnight. Restart Ollama or accept regex-only for the day.
    - **Anthropic 429 rate hit 3x between 02:04 and 02:19.**
      Not a sustained outage; Balanced/Reasoning tier requests retried and succeeded. Watch for a pattern by tomorrow's digest.

    ## Watch

    - **Disk pressure 78% on demo host, +6pp week-over-week.**
      Growth is `data/digests/*.md` accumulating (no rotation) + Ollama model cache. Not urgent; will need pruning within 2 weeks.

    ## Guardrails

    24h counts: PHI redactions 41 (T1 4 / T2 29 / T3 8) · BAA blocks 0 · Injection blocks 2 · Injection flags 1

    ## Systems

    - ollama: red — unreachable since 03:12 UTC
    - anthropic: green — 3x 429s within retry budget
    - host_cpu: green
    - host_memory: green
    - host_disk: yellow — 78% used, trending up
    - hardening: green — all 8 controls compliant

    ## Decisions I need

    - **Restart Ollama or accept regex-only sentinel for today?**
      Fail-open policy is safe (regex catches known-bad), but novel-attack coverage is degraded until Ollama comes back.

## Appendix B — Rendered Mockup: A quiet day

Same structure. Demonstrates that empty sections stay empty — `None.` is the correct output, not filler prose. This is the "did the agent do nothing wrong" mockup: a day with signal absence.

    # SignalCare Ops Digest — 2026-08-15

    ## Attention

    None.

    ## Watch

    - **Disk pressure 79% on demo host.**
      Follow-through from yesterday's Watch item; no action needed today but prune within 10 days.

    ## Guardrails

    24h counts: PHI redactions 38 (T1 5 / T2 25 / T3 8) · BAA blocks 0 · Injection blocks 0 · Injection flags 0

    ## Systems

    - ollama: green
    - anthropic: green
    - host_cpu: green
    - host_memory: green
    - host_disk: yellow — 79% used, trending up
    - hardening: green — all 8 controls compliant

    ## Decisions I need

    None.
