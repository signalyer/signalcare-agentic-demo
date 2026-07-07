"""L3 compliance_ops · Founder Mode daily digest agent.

Balanced-tier synthesis with source-of-truth overrides on the counts and
states that LLMs are known to miscount or mis-observe. See ADR-0008 for
the UX spec and the "LLMs are reformatters, not calculators" principle
behind the overrides.

Daily flow (invoked by the cron trigger scheduled in Session C):

    1. Gather four data sources: host stats (psutil), adapter health
       (concurrent httpx probes), hardening posture (seed file), and
       guardrail activity (parsed log file). See ``.tools``.
    2. Compute the systems array entirely in the agent — state comes
       from tool output, note is a short deterministic string. LLM
       does not influence systems values per ADR-0008 §5.
    3. Render the prompt via the L0 prompt_registry + renderer.
    4. Call the Balanced-tier gateway, which is L2-wrapped (BAA gate +
       PHI redactor + injection sentinel per main.py lifespan).
    5. Parse the JSON response defensively — Ollama occasionally wraps
       its output in prose or code fences, so the same greedy ``{...}``
       fallback used by the sentinel classifier lives here too.
    6. Take LLM's attention / watch / decisions arrays; cap each at 3
       and WARN on overflow.
    7. Overwrite guardrails and systems with computed truth.
    8. Persist ``data/digests/YYYY-MM-DD.json`` and ``.md``.
    9. Return DigestResult for the caller — cron log or admin UI.

The agent CONSUMES the AIGateway via ``app.state`` — it does not wrap it.
Compliance_ops is an L3 agent; guardrails are L2 wrappers. See CLAUDE.md
architecture discipline.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

from L0_observability.prompt_registry import PromptRegistry, PromptRenderer
from L6_adapters.ai_gateway import AIGateway, CompletionRequest, Message

from .renderer import render_markdown
from .tools import (
    AdapterHealth,
    HostStats,
    gather_adapter_health,
    gather_guardrail_activity_24h,
    gather_host_stats,
    load_hardening_status,
)

_logger = logging.getLogger("signalcare.compliance_ops.agent")

_PROMPT_KEY = "compliance_ops_digest"
_ITEM_CAP = 3


@dataclass(frozen=True)
class DigestResult:
    """Observable outcome of one daily run.

    ``caps_triggered`` records section → pre-cap length for any section
    the LLM over-populated. ``guardrail_overrides`` is True iff the LLM's
    ``guardrails`` object differed from source-of-truth counts.
    """

    date: str
    json_path: Path
    markdown_path: Path
    caps_triggered: dict[str, int]
    guardrail_overrides: bool


class ComplianceOpsAgent:
    """The first L3 agent to ship. See module docstring for the flow.

    Dependencies are injected via constructor so the same class runs
    under the FastAPI lifespan and under pytest with stubs.
    """

    def __init__(
        self,
        *,
        gateway: AIGateway,
        registry: PromptRegistry,
        renderer: PromptRenderer,
        digests_dir: Path,
        log_path: Path,
        hardening_path: Path,
        ollama_url: str = "http://localhost:11434",
        anthropic_url: str = "https://api.anthropic.com",
        anthropic_api_key: str | None = None,
        probe_timeout_s: float = 5.0,
        cpu_interval_s: float = 1.0,
        http_client: httpx.AsyncClient | None = None,
    ):
        self._gateway = gateway
        self._registry = registry
        self._renderer = renderer
        self._digests_dir = digests_dir
        self._log_path = log_path
        self._hardening_path = hardening_path
        self._ollama_url = ollama_url
        self._anthropic_url = anthropic_url
        self._anthropic_api_key = anthropic_api_key
        self._probe_timeout_s = probe_timeout_s
        self._cpu_interval_s = cpu_interval_s
        # Optional pre-built client for tests (typically an httpx.AsyncClient
        # wrapping httpx.MockTransport). Production leaves this None and the
        # tools layer creates a short-lived client per probe pass.
        self._http_client = http_client

    async def run_daily(self, *, now: datetime | None = None) -> DigestResult:
        """Generate today's digest end-to-end. Same-day reruns overwrite."""
        now = now or datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        _logger.info("compliance_ops_run_start date=%s", date_str)

        host = gather_host_stats(cpu_interval_s=self._cpu_interval_s)
        health = await gather_adapter_health(
            ollama_url=self._ollama_url,
            anthropic_url=self._anthropic_url,
            anthropic_api_key=self._anthropic_api_key,
            timeout_s=self._probe_timeout_s,
            client=self._http_client,
        )
        hardening = load_hardening_status(self._hardening_path)
        activity = gather_guardrail_activity_24h(self._log_path, now)

        systems_truth = _compute_systems(host, health, hardening)

        definition = self._registry.get(_PROMPT_KEY)
        system_msg, user_msg = self._renderer.render(
            definition,
            host_stats=json.dumps(host.to_prompt_dict()),
            adapter_health=json.dumps(health.to_prompt_dict()),
            hardening_status=json.dumps(hardening),
            guardrail_activity_24h=json.dumps(activity.to_prompt_dict()),
        )

        response = await self._gateway.complete(
            CompletionRequest(
                tier=definition.tier,
                messages=[
                    Message(role="system", content=system_msg),
                    Message(role="user", content=user_msg),
                ],
                max_tokens=definition.max_tokens,
                temperature=definition.temperature,
                trace_id=f"compliance-ops-digest-{date_str}",
            )
        )

        llm_dict = _parse_digest_json(response.text)

        caps_triggered: dict[str, int] = {}
        for section in ("attention", "watch", "decisions"):
            items = llm_dict.get(section) or []
            if not isinstance(items, list):
                _logger.warning(
                    "digest_llm_bad_section date=%s section=%s type=%s",
                    date_str, section, type(items).__name__,
                )
                llm_dict[section] = []
                continue
            if len(items) > _ITEM_CAP:
                caps_triggered[section] = len(items)
                _logger.warning(
                    "digest_llm_cap_enforced date=%s section=%s got=%d cap=%d",
                    date_str, section, len(items), _ITEM_CAP,
                )
                llm_dict[section] = items[:_ITEM_CAP]
            else:
                llm_dict[section] = items

        truth_guardrails = activity.to_prompt_dict()
        guardrail_overrides = llm_dict.get("guardrails") != truth_guardrails
        if guardrail_overrides:
            _logger.warning(
                "digest_llm_guardrails_diverged date=%s llm=%s truth=%s",
                date_str, llm_dict.get("guardrails"), truth_guardrails,
            )
        llm_dict["guardrails"] = truth_guardrails
        llm_dict["systems"] = systems_truth
        llm_dict["date"] = date_str
        llm_dict["generated_at"] = _to_utc_iso(now)

        self._digests_dir.mkdir(parents=True, exist_ok=True)
        json_path = self._digests_dir / f"{date_str}.json"
        markdown_path = self._digests_dir / f"{date_str}.md"
        json_path.write_text(json.dumps(llm_dict, indent=2) + "\n", encoding="utf-8")
        markdown_path.write_text(render_markdown(llm_dict), encoding="utf-8")

        _logger.info(
            "compliance_ops_run_complete date=%s json=%s md=%s caps=%s overrides=%s",
            date_str, json_path, markdown_path, caps_triggered, guardrail_overrides,
        )
        return DigestResult(
            date=date_str,
            json_path=json_path,
            markdown_path=markdown_path,
            caps_triggered=caps_triggered,
            guardrail_overrides=guardrail_overrides,
        )


# ------------------------------------------------------------------ helpers


def _compute_systems(
    host: HostStats,
    health: AdapterHealth,
    hardening: dict,
) -> list[dict]:
    """Produce the systems array with source-of-truth states + short notes.

    LLM does not influence any field here — ADR-0008 §5 puts states
    outside the LLM's arithmetic risk.
    """
    controls = hardening.get("controls", []) if isinstance(hardening, dict) else []
    warning = sum(
        1 for c in controls if isinstance(c, dict) and c.get("state") == "warning"
    )
    failing = sum(
        1 for c in controls if isinstance(c, dict) and c.get("state") == "failing"
    )
    total = len(controls)
    if failing > 0:
        hardening_state = "red"
        hardening_note = f"{failing}/{total} controls failing"
    elif warning > 0:
        hardening_state = "yellow"
        hardening_note = f"{warning}/{total} controls warning"
    else:
        hardening_state = "green"
        hardening_note = f"all {total} controls compliant"

    return [
        {"name": "ollama", "state": health.ollama.state, "note": health.ollama.note},
        {
            "name": "anthropic",
            "state": health.anthropic.state,
            "note": health.anthropic.note,
        },
        {
            "name": "host_cpu",
            "state": _pct_to_state(host.cpu_pct, warn=70, alarm=90),
            "note": _pct_note(host.cpu_pct, warn=70, alarm=90),
        },
        {
            "name": "host_memory",
            "state": _pct_to_state(host.memory_pct, warn=80, alarm=95),
            "note": _pct_note(host.memory_pct, warn=80, alarm=95),
        },
        {
            "name": "host_disk",
            "state": _pct_to_state(host.disk_pct, warn=75, alarm=90),
            "note": _pct_note(host.disk_pct, warn=75, alarm=90),
        },
        {"name": "hardening", "state": hardening_state, "note": hardening_note},
    ]


def _pct_to_state(pct: float, *, warn: float, alarm: float) -> str:
    if pct >= alarm:
        return "red"
    if pct >= warn:
        return "yellow"
    return "green"


def _pct_note(pct: float, *, warn: float, alarm: float) -> str | None:
    """Short note when the state is not green. None when unremarkable."""
    if pct >= alarm:
        return f"{pct:.0f}% used — alarm"
    if pct >= warn:
        return f"{pct:.0f}% used — trending up"
    return None


def _to_utc_iso(when: datetime) -> str:
    """Convert naive-or-aware datetime to a stable UTC ISO string."""
    if when.tzinfo is None:
        return when.replace(tzinfo=UTC).isoformat()
    return when.astimezone(UTC).isoformat()


def _parse_digest_json(raw: str) -> dict:
    """Extract a JSON object from LLM output.

    Fall back to a greedy ``{...}`` extraction when the model wraps its
    output in prose or code fences — the same defensive shape as the
    injection sentinel's classifier parser. A well-behaved model returns
    raw JSON with no surrounding chatter.
    """
    stripped = raw.strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            _logger.warning("digest_llm_no_json_object raw=%r", stripped[:200])
            return {}
        try:
            parsed = json.loads(stripped[start : end + 1])
        except json.JSONDecodeError as exc:
            _logger.warning("digest_llm_json_parse_error err=%s", exc)
            return {}
    if not isinstance(parsed, dict):
        _logger.warning(
            "digest_llm_top_level_not_object type=%s", type(parsed).__name__
        )
        return {}
    return parsed
