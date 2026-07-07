"""Unit tests for L3 compliance_ops agent + tools + renderer.

Offline. No live Ollama, no live Anthropic, no live filesystem outside
tmp_path. Coverage per Session B test plan:

    - Renderer produces the exact ADR-0008 Appendix A / B markdown.
    - Renderer handles empty sections with "None." literal.
    - Guardrails single-line format matches ADR-0008.
    - Systems entries render note only when non-null.
    - Log parser counts every canonical L2 log line correctly.
    - Log parser missing file → all zeros (fresh install).
    - Log parser respects the 24h window.
    - Log parser records lines_skipped for malformed input.
    - Hardening loader is loud on missing / malformed files.
    - Host stats returns floats in [0, 100].
    - Adapter probes: green / yellow / red / 401 / unreachable transitions.
    - Anthropic probe yellow when no api key configured.
    - Agent run_daily happy path — writes both .json and .md.
    - Agent overwrites LLM's guardrails from truth (WARN + DigestResult flag).
    - Agent caps arrays at 3 (WARN + DigestResult flag).
    - Agent JSON parser handles prose-wrapped output (Ollama defensive).
    - Agent JSON parser survives non-JSON output (empty dict + WARN).
"""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from pathlib import Path
from textwrap import dedent

import httpx
import pytest

from L3_agents.compliance_ops import ComplianceOpsAgent, DigestResult, render_markdown
from L3_agents.compliance_ops.agent import _compute_systems, _parse_digest_json
from L3_agents.compliance_ops.tools import (
    AdapterHealth,
    GuardrailActivity,
    HostStats,
    ProbeResult,
    gather_adapter_health,
    gather_guardrail_activity_24h,
    gather_host_stats,
    load_hardening_status,
)
from L0_observability.prompt_registry import (
    FileBackedPromptRegistry,
    PromptRenderer,
)
from L6_adapters.ai_gateway import (
    AIGateway,
    CompletionRequest,
    CompletionResponse,
    Tier,
)


# ------------------------------------------------------------------ fixtures


class _CapturingGateway(AIGateway):
    """Fake gateway. Records requests and returns a canned text body."""

    provider_name = "capturing"

    def __init__(self, response_text: str = "{}"):
        self._response_text = response_text
        self.received: list[CompletionRequest] = []

    def supports_tier(self, tier: Tier) -> bool:  # noqa: ARG002
        return True

    def vendor_for(self, tier: Tier) -> str:  # noqa: ARG002
        return "capturing"

    async def complete(self, req: CompletionRequest) -> CompletionResponse:
        self.received.append(req)
        return CompletionResponse(
            text=self._response_text,
            model="capturing-model",
            provider="capturing",
            tokens_in=0,
            tokens_out=0,
            latency_ms=0,
            trace_id=req.trace_id,
        )

    async def stream(self, req: CompletionRequest) -> AsyncIterator[str]:  # noqa: ARG002
        yield self._response_text

    async def close(self) -> None:
        pass


_REAL_PROMPTS_DIR = (
    Path(__file__).resolve().parents[2] / "app" / "L0_observability" / "prompts"
)


@pytest.fixture
def registry():
    return FileBackedPromptRegistry(prompts_dir=_REAL_PROMPTS_DIR, state_file=None)


@pytest.fixture
def hardening_path(tmp_path: Path) -> Path:
    path = tmp_path / "hardening.json"
    path.write_text(
        json.dumps(
            {
                "controls": [
                    {"id": "one", "state": "compliant"},
                    {"id": "two", "state": "compliant"},
                    {"id": "three", "state": "compliant"},
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


def _make_agent(
    tmp_path: Path,
    hardening_path: Path,
    registry: FileBackedPromptRegistry,
    *,
    gateway: AIGateway,
    http_client: httpx.AsyncClient,
    log_path: Path | None = None,
) -> ComplianceOpsAgent:
    return ComplianceOpsAgent(
        gateway=gateway,
        registry=registry,
        renderer=PromptRenderer(),
        digests_dir=tmp_path / "digests",
        log_path=log_path or (tmp_path / "signalcare.log"),
        hardening_path=hardening_path,
        ollama_url="http://ollama.test",
        anthropic_url="http://anthropic.test",
        anthropic_api_key="test-key",
        probe_timeout_s=1.0,
        cpu_interval_s=0.01,
        http_client=http_client,
    )


def _default_http_client() -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": []})
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": []})
        return httpx.Response(404)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# ------------------------------------------------------------------ renderer


_APPENDIX_A = dedent(
    """\
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
    """
)


_APPENDIX_B = dedent(
    """\
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
    """
)


def test_renderer_matches_adr0008_appendix_a():
    digest = {
        "date": "2026-08-14",
        "attention": [
            {
                "headline": "Ollama unreachable since 03:12; injection sentinel degraded to regex-only.",
                "evidence": (
                    "Fail-open logged 47 sentinel-classifier-error lines overnight. "
                    "Restart Ollama or accept regex-only for the day."
                ),
            },
            {
                "headline": "Anthropic 429 rate hit 3x between 02:04 and 02:19.",
                "evidence": (
                    "Not a sustained outage; Balanced/Reasoning tier requests retried and "
                    "succeeded. Watch for a pattern by tomorrow's digest."
                ),
            },
        ],
        "watch": [
            {
                "headline": "Disk pressure 78% on demo host, +6pp week-over-week.",
                "evidence": (
                    "Growth is `data/digests/*.md` accumulating (no rotation) + Ollama "
                    "model cache. Not urgent; will need pruning within 2 weeks."
                ),
            }
        ],
        "guardrails": {
            "phi_redactions": {"total": 41, "T1": 4, "T2": 29, "T3": 8},
            "baa_blocks": 0,
            "injection_blocks": 2,
            "injection_flags": 1,
        },
        "systems": [
            {"name": "ollama", "state": "red", "note": "unreachable since 03:12 UTC"},
            {"name": "anthropic", "state": "green", "note": "3x 429s within retry budget"},
            {"name": "host_cpu", "state": "green", "note": None},
            {"name": "host_memory", "state": "green", "note": None},
            {"name": "host_disk", "state": "yellow", "note": "78% used, trending up"},
            {"name": "hardening", "state": "green", "note": "all 8 controls compliant"},
        ],
        "decisions": [
            {
                "question": "Restart Ollama or accept regex-only sentinel for today?",
                "context": (
                    "Fail-open policy is safe (regex catches known-bad), but novel-attack "
                    "coverage is degraded until Ollama comes back."
                ),
            }
        ],
    }
    assert render_markdown(digest) == _APPENDIX_A


def test_renderer_matches_adr0008_appendix_b_quiet_day():
    digest = {
        "date": "2026-08-15",
        "attention": [],
        "watch": [
            {
                "headline": "Disk pressure 79% on demo host.",
                "evidence": (
                    "Follow-through from yesterday's Watch item; no action needed today "
                    "but prune within 10 days."
                ),
            }
        ],
        "guardrails": {
            "phi_redactions": {"total": 38, "T1": 5, "T2": 25, "T3": 8},
            "baa_blocks": 0,
            "injection_blocks": 0,
            "injection_flags": 0,
        },
        "systems": [
            {"name": "ollama", "state": "green", "note": None},
            {"name": "anthropic", "state": "green", "note": None},
            {"name": "host_cpu", "state": "green", "note": None},
            {"name": "host_memory", "state": "green", "note": None},
            {"name": "host_disk", "state": "yellow", "note": "79% used, trending up"},
            {"name": "hardening", "state": "green", "note": "all 8 controls compliant"},
        ],
        "decisions": [],
    }
    assert render_markdown(digest) == _APPENDIX_B


def test_renderer_missing_optional_keys_defaults_to_empty():
    # Defensive: agent should always ship well-formed input, but if a key is
    # missing the renderer should still produce all five sections rather than
    # crash. Guardrails counts default to 0.
    result = render_markdown({"date": "2026-01-01"})
    assert "## Attention" in result
    assert "## Watch" in result
    assert "## Guardrails" in result
    assert "24h counts: PHI redactions 0 (T1 0 / T2 0 / T3 0)" in result
    assert "## Systems" in result
    assert "## Decisions I need" in result
    # Empty sections say "None."
    assert result.count("None.") == 4  # attention, watch, systems, decisions


# ------------------------------------------------------------------ hardening loader


def test_load_hardening_status_happy(hardening_path: Path):
    data = load_hardening_status(hardening_path)
    assert isinstance(data.get("controls"), list)
    assert len(data["controls"]) == 3


def test_load_hardening_status_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="hardening seed file not found"):
        load_hardening_status(tmp_path / "missing.json")


def test_load_hardening_status_bad_json_raises(tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text("not json {", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        load_hardening_status(bad)


def test_load_hardening_status_missing_controls_raises(tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"no_controls_here": True}), encoding="utf-8")
    with pytest.raises(ValueError, match="missing 'controls' array"):
        load_hardening_status(bad)


# ------------------------------------------------------------------ host stats


def test_gather_host_stats_returns_floats_in_range():
    stats = gather_host_stats(cpu_interval_s=0.01)
    assert isinstance(stats, HostStats)
    assert 0.0 <= stats.cpu_pct <= 100.0
    assert 0.0 <= stats.memory_pct <= 100.0
    assert 0.0 <= stats.disk_pct <= 100.0


# ------------------------------------------------------------------ log parser


def _log_line(ts: datetime, logger_name: str, message: str) -> str:
    """Mimic Python logging default format for testing."""
    return (
        f"{ts.strftime('%Y-%m-%d %H:%M:%S')},{ts.microsecond // 1000:03d} "
        f"INFO {logger_name} {message}\n"
    )


def test_log_parser_missing_file_returns_zeros(tmp_path: Path):
    activity = gather_guardrail_activity_24h(
        tmp_path / "no_such_log.log", now=datetime(2026, 8, 14, 6, 30)
    )
    assert activity.phi_redactions_total == 0
    assert activity.baa_blocks == 0
    assert activity.injection_blocks == 0
    assert activity.injection_flags == 0
    assert activity.lines_parsed == 0


def test_log_parser_counts_all_l2_line_types(tmp_path: Path):
    log_path = tmp_path / "signalcare.log"
    now = datetime(2026, 8, 14, 6, 30)
    lines = []
    # 4 x T1 redactions
    for _ in range(4):
        lines.append(
            _log_line(
                now - timedelta(hours=1),
                "signalcare.phi_redactor",
                "phi_scan phi_present=True phi_tier=T1 mode=strict trace_id=abc",
            )
        )
    # 29 x T2 redactions
    for _ in range(29):
        lines.append(
            _log_line(
                now - timedelta(hours=2),
                "signalcare.phi_redactor",
                "phi_scan phi_present=True phi_tier=T2 mode=strict trace_id=xyz",
            )
        )
    # 8 x T3 redactions
    for _ in range(8):
        lines.append(
            _log_line(
                now - timedelta(hours=3),
                "signalcare.phi_redactor",
                "phi_scan phi_present=True phi_tier=T3 mode=strict trace_id=lmn",
            )
        )
    # phi_present=False lines that must NOT be counted
    for _ in range(50):
        lines.append(
            _log_line(
                now - timedelta(hours=1),
                "signalcare.phi_redactor",
                "phi_scan phi_present=False phi_tier=None mode=strict trace_id=noise",
            )
        )
    # 2 x injection blocks + 1 flag + 3 allow (allow must NOT count)
    lines.append(
        _log_line(
            now - timedelta(hours=1),
            "signalcare.injection_sentinel",
            "injection_sentinel_decision decision=deny source=regex pattern=abc trace_id=1",
        )
    )
    lines.append(
        _log_line(
            now - timedelta(hours=2),
            "signalcare.injection_sentinel",
            "injection_sentinel_decision decision=deny source=llm pattern=xyz trace_id=2",
        )
    )
    lines.append(
        _log_line(
            now - timedelta(hours=3),
            "signalcare.injection_sentinel",
            "injection_sentinel_decision decision=flag source=regex pattern=lmn trace_id=3",
        )
    )
    for _ in range(3):
        lines.append(
            _log_line(
                now - timedelta(hours=1),
                "signalcare.injection_sentinel",
                "injection_sentinel_decision decision=allow reason=no_hit trace_id=4",
            )
        )
    # BAA gate: 0 denies (all allow paths must NOT count)
    lines.append(
        _log_line(
            now - timedelta(hours=1),
            "signalcare.baa_gate",
            "baa_gate_decision decision=allow reason=vendor_approved vendor=anthropic tier=balanced phi_tier=T2 trace_id=a",
        )
    )
    lines.append(
        _log_line(
            now - timedelta(hours=1),
            "signalcare.baa_gate",
            "baa_gate_decision decision=allow reason=no_phi vendor=anthropic tier=balanced trace_id=b",
        )
    )
    log_path.write_text("".join(lines), encoding="utf-8")

    activity = gather_guardrail_activity_24h(log_path, now=now)
    assert activity.phi_redactions_by_tier == {"T1": 4, "T2": 29, "T3": 8}
    assert activity.phi_redactions_total == 41
    assert activity.injection_blocks == 2
    assert activity.injection_flags == 1
    assert activity.baa_blocks == 0


def test_log_parser_respects_24h_window(tmp_path: Path):
    log_path = tmp_path / "signalcare.log"
    now = datetime(2026, 8, 14, 6, 30)
    lines = [
        # Inside window
        _log_line(
            now - timedelta(hours=1),
            "signalcare.injection_sentinel",
            "injection_sentinel_decision decision=deny source=regex pattern=one trace_id=inside",
        ),
        # OUTSIDE window (25h ago)
        _log_line(
            now - timedelta(hours=25),
            "signalcare.injection_sentinel",
            "injection_sentinel_decision decision=deny source=regex pattern=old trace_id=outside",
        ),
    ]
    log_path.write_text("".join(lines), encoding="utf-8")
    activity = gather_guardrail_activity_24h(log_path, now=now)
    assert activity.injection_blocks == 1


def test_log_parser_counts_baa_denies(tmp_path: Path):
    log_path = tmp_path / "signalcare.log"
    now = datetime(2026, 8, 14, 6, 30)
    lines = [
        _log_line(
            now - timedelta(minutes=30),
            "signalcare.baa_gate",
            "baa_gate_decision decision=deny reason=unapproved_vendor_with_phi vendor=other tier=fast phi_tier=T1 trace_id=x",
        )
    ] * 3
    log_path.write_text("".join(lines), encoding="utf-8")
    activity = gather_guardrail_activity_24h(log_path, now=now)
    assert activity.baa_blocks == 3


def test_log_parser_records_skipped_for_malformed(tmp_path: Path):
    log_path = tmp_path / "signalcare.log"
    log_path.write_text(
        "no timestamp here\n"
        "also not a log line\n"
        "2026-08-14 06:00:00,000 INFO signalcare.injection_sentinel "
        "injection_sentinel_decision decision=deny source=regex pattern=x trace_id=1\n",
        encoding="utf-8",
    )
    activity = gather_guardrail_activity_24h(
        log_path, now=datetime(2026, 8, 14, 6, 30)
    )
    assert activity.lines_skipped == 2
    assert activity.injection_blocks == 1


# ------------------------------------------------------------------ adapter probes


@pytest.mark.asyncio
async def test_adapter_probes_both_green():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={})
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={})
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        health = await gather_adapter_health(
            ollama_url="http://o.test",
            anthropic_url="http://a.test",
            anthropic_api_key="key",
            client=client,
        )
    finally:
        await client.aclose()
    assert health.ollama.state == "green"
    assert health.anthropic.state == "green"


@pytest.mark.asyncio
async def test_anthropic_probe_401_is_red():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(401)
        return httpx.Response(200, json={})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        health = await gather_adapter_health(
            ollama_url="http://o.test",
            anthropic_url="http://a.test",
            anthropic_api_key="bad-key",
            client=client,
        )
    finally:
        await client.aclose()
    assert health.anthropic.state == "red"
    assert "401" in (health.anthropic.note or "")


@pytest.mark.asyncio
async def test_anthropic_probe_yellow_when_no_api_key():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        health = await gather_adapter_health(
            ollama_url="http://o.test",
            anthropic_url="http://a.test",
            anthropic_api_key=None,
            client=client,
        )
    finally:
        await client.aclose()
    assert health.anthropic.state == "yellow"
    assert "no api key" in (health.anthropic.note or "")


@pytest.mark.asyncio
async def test_ollama_probe_unreachable_is_red():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        health = await gather_adapter_health(
            ollama_url="http://o.test",
            anthropic_url="http://a.test",
            anthropic_api_key="key",
            client=client,
        )
    finally:
        await client.aclose()
    assert health.ollama.state == "red"
    assert "ConnectError" in (health.ollama.note or "")


# ------------------------------------------------------------------ _compute_systems


def test_compute_systems_reflects_probe_states_and_percentages():
    host = HostStats(cpu_pct=12.0, memory_pct=45.0, disk_pct=82.0)
    health = AdapterHealth(
        ollama=ProbeResult("red", "unreachable", None),
        anthropic=ProbeResult("green", None, 250),
    )
    hardening = {
        "controls": [
            {"state": "compliant"},
            {"state": "compliant"},
            {"state": "warning"},
        ]
    }
    systems = _compute_systems(host, health, hardening)
    by_name = {s["name"]: s for s in systems}
    assert by_name["ollama"]["state"] == "red"
    assert by_name["anthropic"]["state"] == "green"
    assert by_name["host_cpu"]["state"] == "green"
    assert by_name["host_memory"]["state"] == "green"
    assert by_name["host_disk"]["state"] == "yellow"  # 82% > 75 warn threshold
    assert by_name["hardening"]["state"] == "yellow"  # one control warning
    assert "1/3 controls warning" == by_name["hardening"]["note"]


# ------------------------------------------------------------------ _parse_digest_json


def test_parse_digest_json_plain_object():
    parsed = _parse_digest_json('{"attention": [], "watch": []}')
    assert parsed == {"attention": [], "watch": []}


def test_parse_digest_json_survives_prose_wrapping():
    # Ollama sometimes leads with "Here is the JSON:" — we grep {…} greedily.
    parsed = _parse_digest_json(
        'Sure! Here is your digest.\n\n{"attention": [{"headline": "x", "evidence": "y"}]}\n\nHope that helps.'
    )
    assert parsed == {"attention": [{"headline": "x", "evidence": "y"}]}


def test_parse_digest_json_returns_empty_on_garbage():
    assert _parse_digest_json("total nonsense no braces here") == {}


def test_parse_digest_json_returns_empty_on_non_object_top_level():
    assert _parse_digest_json("[1, 2, 3]") == {}


# ------------------------------------------------------------------ agent


def _valid_llm_response(*, attention_count: int = 1, guardrails: dict | None = None) -> str:
    """Build a well-formed LLM response for the CapturingGateway to return."""
    guardrails = guardrails or {
        "phi_redactions": {"total": 0, "T1": 0, "T2": 0, "T3": 0},
        "baa_blocks": 0,
        "injection_blocks": 0,
        "injection_flags": 0,
    }
    return json.dumps(
        {
            "date": "will-be-overwritten",
            "generated_at": "will-be-overwritten",
            "attention": [
                {"headline": f"item {i}", "evidence": f"ev {i}"}
                for i in range(attention_count)
            ],
            "watch": [],
            "guardrails": guardrails,
            "systems": [],
            "decisions": [],
        }
    )


@pytest.mark.asyncio
async def test_agent_run_daily_writes_both_files(
    tmp_path: Path,
    hardening_path: Path,
    registry: FileBackedPromptRegistry,
):
    gateway = _CapturingGateway(_valid_llm_response())
    client = _default_http_client()
    try:
        agent = _make_agent(
            tmp_path, hardening_path, registry, gateway=gateway, http_client=client
        )
        result = await agent.run_daily(now=datetime(2026, 8, 14, 6, 30))
    finally:
        await client.aclose()
    assert isinstance(result, DigestResult)
    assert result.date == "2026-08-14"
    assert result.json_path.exists()
    assert result.markdown_path.exists()
    data = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert data["date"] == "2026-08-14"
    md = result.markdown_path.read_text(encoding="utf-8")
    assert "# SignalCare Ops Digest — 2026-08-14" in md


@pytest.mark.asyncio
async def test_agent_overwrites_guardrails_from_truth(
    tmp_path: Path,
    hardening_path: Path,
    registry: FileBackedPromptRegistry,
    caplog: pytest.LogCaptureFixture,
):
    # LLM claims a random count. Log file is empty (missing) → truth is 0s.
    liar_guardrails = {
        "phi_redactions": {"total": 999, "T1": 999, "T2": 999, "T3": 999},
        "baa_blocks": 99,
        "injection_blocks": 99,
        "injection_flags": 99,
    }
    gateway = _CapturingGateway(_valid_llm_response(guardrails=liar_guardrails))
    client = _default_http_client()
    try:
        agent = _make_agent(
            tmp_path, hardening_path, registry, gateway=gateway, http_client=client
        )
        with caplog.at_level(logging.WARNING, logger="signalcare.compliance_ops.agent"):
            result = await agent.run_daily(now=datetime(2026, 8, 14, 6, 30))
    finally:
        await client.aclose()
    assert result.guardrail_overrides is True
    data = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert data["guardrails"]["phi_redactions"]["total"] == 0
    assert data["guardrails"]["baa_blocks"] == 0
    assert any(
        "digest_llm_guardrails_diverged" in rec.message for rec in caplog.records
    )


@pytest.mark.asyncio
async def test_agent_caps_attention_at_three(
    tmp_path: Path,
    hardening_path: Path,
    registry: FileBackedPromptRegistry,
    caplog: pytest.LogCaptureFixture,
):
    gateway = _CapturingGateway(_valid_llm_response(attention_count=5))
    client = _default_http_client()
    try:
        agent = _make_agent(
            tmp_path, hardening_path, registry, gateway=gateway, http_client=client
        )
        with caplog.at_level(logging.WARNING, logger="signalcare.compliance_ops.agent"):
            result = await agent.run_daily(now=datetime(2026, 8, 14, 6, 30))
    finally:
        await client.aclose()
    assert result.caps_triggered == {"attention": 5}
    data = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert len(data["attention"]) == 3
    assert any(
        "digest_llm_cap_enforced" in rec.message and "attention" in rec.message
        for rec in caplog.records
    )


@pytest.mark.asyncio
async def test_agent_uses_computed_systems_not_llm_systems(
    tmp_path: Path,
    hardening_path: Path,
    registry: FileBackedPromptRegistry,
):
    # LLM outputs bogus systems entries; agent must throw them away and use
    # its own computed truth (from tools + hardening file).
    bad_llm_response = json.dumps(
        {
            "attention": [],
            "watch": [],
            "decisions": [],
            "guardrails": {
                "phi_redactions": {"total": 0, "T1": 0, "T2": 0, "T3": 0},
                "baa_blocks": 0,
                "injection_blocks": 0,
                "injection_flags": 0,
            },
            "systems": [{"name": "not_a_real_system", "state": "purple", "note": "lol"}],
        }
    )
    gateway = _CapturingGateway(bad_llm_response)
    client = _default_http_client()
    try:
        agent = _make_agent(
            tmp_path, hardening_path, registry, gateway=gateway, http_client=client
        )
        result = await agent.run_daily(now=datetime(2026, 8, 14, 6, 30))
    finally:
        await client.aclose()
    data = json.loads(result.json_path.read_text(encoding="utf-8"))
    names = {s["name"] for s in data["systems"]}
    assert names == {"ollama", "anthropic", "host_cpu", "host_memory", "host_disk", "hardening"}
    assert "not_a_real_system" not in names


@pytest.mark.asyncio
async def test_agent_sends_balanced_tier_and_correct_prompt_key(
    tmp_path: Path,
    hardening_path: Path,
    registry: FileBackedPromptRegistry,
):
    gateway = _CapturingGateway(_valid_llm_response())
    client = _default_http_client()
    try:
        agent = _make_agent(
            tmp_path, hardening_path, registry, gateway=gateway, http_client=client
        )
        await agent.run_daily(now=datetime(2026, 8, 14, 6, 30))
    finally:
        await client.aclose()
    assert len(gateway.received) == 1
    sent = gateway.received[0]
    assert sent.tier == Tier.BALANCED
    assert sent.max_tokens == 1200
    assert sent.temperature == pytest.approx(0.2)
    # The prompt SHOULD have the JSON schema block inlined by the renderer.
    user_msg = next(m for m in sent.messages if m.role == "user")
    assert "output_schema" not in user_msg.content or '"attention"' in user_msg.content
