# ADR-0004 — Direct Provider SDKs Instead of OpenRouter Gateway Proxy

**Status:** Accepted
**Date:** 2026-07-07
**Deciders:** Solo founder

## Context

The scaffold session (Phase 0, ADR-0002) landed on a single hosted AI adapter — `openrouter.py` — that routed Balanced and Reasoning tiers through OpenRouter, an OpenAI-compatible proxy in front of Claude, GPT, and other model families. The rationale at the time was simplicity: one HTTP surface, one client library, one billing surface.

Phase 1 live verification surfaced two facts:

1. **The user's `.env` already carries direct provider credentials** — `ANTHROPIC_API_KEY` (108 chars, valid) and `OPENAI_API_KEY` (164 chars, valid) — not just `OPENROUTER_API_KEY`. Direct-SDK access was available before the proxy was needed.
2. **The first live Reasoning-tier call through OpenRouter failed with `402 Insufficient credits`.** Not a code bug — a billing state. The user's OpenRouter account had never purchased credits, so every hosted call would 402 until $10+ was spent. That is an *external business dependency* the demo doesn't need to carry.

Broader forces:

- **Audience matters.** Enterprise architects reading this repo will read `openrouter.py` and ask "why introduce a proxy for something the two SDKs handle natively?" — a question with no good answer given the direct keys were already available.
- **The ADR-0002 abstraction claim gets *stronger* under direct SDKs.** With OpenRouter, `openrouter.py` handles Claude and GPT with the same code path (both are OpenAI-compatible under OpenRouter's translation). With direct SDKs, we'd have `anthropic_gateway.py` calling `AsyncAnthropic.messages.create()` and (potentially) `openai_gateway.py` calling `AsyncOpenAI.chat.completions.create()` — two genuinely different provider surface areas flattened to the same `CompletionResponse` shape. That is a real abstraction demonstration.
- **`anthropic>=0.40` and `openai>=1.60` are already in `pyproject.toml`.** The pivot cost is code, not new dependencies.

## Decision

For hosted tiers (Balanced, Reasoning), use the **Anthropic SDK directly**. Remove `openrouter.py` from the codebase.

- **`app/L6_adapters/ai_gateway/anthropic_gateway.py`** — implements `AIGateway` using `anthropic.AsyncAnthropic.messages.create()` and `.stream()`. Handles the SDK's quirks:
  - `system` is a top-level parameter, not a message role; the adapter extracts and separates it.
  - `max_tokens` is required, not optional.
  - Response text lives at `resp.content[0].text`; usage counters are `input_tokens` / `output_tokens`.
- **`router.py`** — updated dispatch: Fast → `OllamaGateway`, Balanced/Reasoning → `AnthropicGateway`.
- **OpenAI direct adapter** is *not* implemented in this ADR. The user's `OPENAI_API_KEY` remains in `.env` for future use (e.g., a `gpt_gateway.py` sibling for adversarial-verify or cost-diverse ensembles in Phase 7), but adding it now is scope creep. The single-hosted-provider setup already proves the ADR-0002 claim; adding a second is an ADR of its own when needed.

Model IDs come from env vars:
- `ANTHROPIC_REASONING_MODEL` (default `claude-opus-4-7`, per global `CLAUDE.md`)
- `ANTHROPIC_BALANCED_MODEL` (default `claude-sonnet-4-6`)

## Consequences

### Positive

- **Zero external business dependency for the hosted tier.** Anthropic's uptime and billing are already trusted for the broader SignalCare stack.
- **The ADR-0002 abstraction claim now demonstrates two genuinely different provider surfaces** (Ollama REST + Anthropic SDK) rather than "two Anthropic-compatible endpoints behind one proxy."
- **`openrouter.py` deletion simplifies the repo.** One fewer file, one fewer set of env vars, one fewer failure mode.
- **The user's existing Anthropic key works immediately** — live verification unblocked without buying credits elsewhere.
- **Consistent with enterprise architect expectations** — direct SDK per provider is the production-shape default.

### Negative

- **Adding a second hosted provider (e.g., OpenAI) is now a code change** (write a new adapter), not a config change (add a model ID to env). Trade-off worth accepting: multi-provider is a Phase 7 concern, not a Phase 1 concern.
- **Anthropic-specific behavior leaks into `anthropic_gateway.py`** in ways that would be masked by a proxy — `system` splitting, differing usage-field names. This is documentation of reality, not a leak of the abstraction: the *interface* (`AIGateway`) stays provider-agnostic; only the *implementation* deals with Anthropic quirks.
- **Any prior references to `OpenRouterGateway` in tests or docs need updating.** Handled in the same commit as the code change.

### Neutral / Notable

- **The `openai>=1.60` dependency stays in `pyproject.toml`.** Removing it is scope creep; keeping it costs nothing and enables the future OpenAI adapter without a dependency-management cycle.
- **The `OPENROUTER_*` env vars in `.env.example` are removed.** Anyone using the pre-ADR-0004 example file will need to update. Migration is: remove `OPENROUTER_API_KEY` and OpenRouter model IDs; ensure `ANTHROPIC_API_KEY` is set.
- **This ADR does not change ADR-0002's claim.** ADR-0002 says "every external platform dependency is expressed as an abstract base class with concrete implementations." That still holds. ADR-0004 just picks a different concrete implementation for the hosted tier.

## Alternatives Considered

- **Buy OpenRouter credits ($10+) and keep the proxy adapter.** Rejected on principle: adds an ongoing external business dependency the demo doesn't need. Also weakens the abstraction demo (Claude and GPT through OpenRouter share ~95% of the adapter code path; direct SDKs share ~0%).
- **Implement both `anthropic_gateway.py` and `openai_gateway.py` simultaneously.** Rejected as premature. A single hosted provider is enough to prove ADR-0002. OpenAI can land in Phase 7 when adversarial-verify needs a second, diverse-provider signal.
- **Keep `openrouter.py` alongside `anthropic_gateway.py` as an alternate.** Rejected — creates ambiguity ("which one is canonical?") without a benefit until someone actually needs OpenRouter. YAGNI.
- **Pivot to a fully vendor-neutral abstraction library (e.g., `litellm`).** Rejected on the same grounds ADR-0002 rejected higher-level libraries — the interface is small enough to hand-roll, and pulling in a large library to justify one demo would obscure the pattern the audience is here to see.

## References

- ADR-0002 (Cloud-Agnostic Adapter Pattern) — this ADR selects a concrete impl; does not alter the substrate contract
- Live test transcript that triggered this decision (session 2026-07-07):
  - Anthropic key valid, model pull complete, Ollama Fast tier verified at 601 ms warm
  - OpenRouter call: `POST openrouter.ai/api/v1/chat/completions → 402 Insufficient credits` (trace_id `echo-2447dc5b5cbf`)
- Anthropic SDK: <https://docs.anthropic.com/claude/reference/messages>
- Related upcoming Phase 7 work: adversarial-verify multi-provider ensemble may reintroduce OpenAI as `openai_gateway.py` sibling
