"""L3 compliance_ops · data-source tools for the Founder Mode digest.

Four gatherers feeding the digest per ADR-0008 §7. Each returns a frozen
dataclass so the agent has a typed shape to pass to the LLM (as JSON in
the evidence bundle) AND to overwrite the LLM's ``guardrails`` object
with source-of-truth counts before persistence.

    - ``gather_host_stats()`` — psutil CPU / memory / disk %.
    - ``gather_adapter_health(...)`` — httpx probes for Ollama + Anthropic.
    - ``load_hardening_status(path)`` — reads ``data/seed/hardening_status.json``.
    - ``gather_guardrail_activity_24h(log_path, now, window_hours=24)`` —
      greps the rotating L2 log file for decision lines and counts them.

Non-goals for Session B
-----------------------
- No caching between calls. Digest runs once/day; recompute is fine.
- No retries on adapter probes. A probe that times out IS a red signal.
- No stitched read across rotated log files (``.log.1``, ``.log.2``).
  Session B reads the current file only; a Phase 3 audit tool can
  walk the archive if a 30-day retrospective is needed.
- No JSON structured logging. Phase 3 replaces the plain-text parser
  with a JSON-lines reader when the OTEL/structlog pipeline lands.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import psutil

_logger = logging.getLogger("signalcare.compliance_ops.tools")


# ------------------------------------------------------------------ value types


@dataclass(frozen=True)
class HostStats:
    """CPU / memory / disk usage percentages, each in ``[0.0, 100.0]``."""

    cpu_pct: float
    memory_pct: float
    disk_pct: float

    def to_prompt_dict(self) -> dict:
        return {
            "cpu_pct": round(self.cpu_pct, 1),
            "memory_pct": round(self.memory_pct, 1),
            "disk_pct": round(self.disk_pct, 1),
        }


@dataclass(frozen=True)
class ProbeResult:
    """One adapter's reachability check.

    ``state`` is the ADR-0008 §5 systems vocabulary (green|yellow|red).
    ``note`` is null when nothing worth saying (green + fast); otherwise
    a short human-readable diagnostic. ``reached_ms`` is the observed
    round-trip when the socket connected at all, else None.
    """

    state: str
    note: str | None
    reached_ms: int | None


@dataclass(frozen=True)
class AdapterHealth:
    ollama: ProbeResult
    anthropic: ProbeResult

    def to_prompt_dict(self) -> dict:
        return {
            "ollama": {
                "state": self.ollama.state,
                "note": self.ollama.note,
                "reached_ms": self.ollama.reached_ms,
            },
            "anthropic": {
                "state": self.anthropic.state,
                "note": self.anthropic.note,
                "reached_ms": self.anthropic.reached_ms,
            },
        }


@dataclass(frozen=True)
class GuardrailActivity:
    """Counts of L2 decision lines in a rolling window.

    ``phi_redactions_by_tier`` is a dict with keys T1/T2/T3 — never None,
    always all three keys present so the digest schema is stable. Values
    default to 0 for tiers that saw no activity.
    """

    phi_redactions_total: int
    phi_redactions_by_tier: dict[str, int]
    baa_blocks: int
    injection_blocks: int
    injection_flags: int
    lines_parsed: int
    lines_skipped: int

    def to_prompt_dict(self) -> dict:
        return {
            "phi_redactions": {
                "total": self.phi_redactions_total,
                "T1": self.phi_redactions_by_tier.get("T1", 0),
                "T2": self.phi_redactions_by_tier.get("T2", 0),
                "T3": self.phi_redactions_by_tier.get("T3", 0),
            },
            "baa_blocks": self.baa_blocks,
            "injection_blocks": self.injection_blocks,
            "injection_flags": self.injection_flags,
        }


# ------------------------------------------------------------------ host stats


def gather_host_stats(*, cpu_interval_s: float = 1.0) -> HostStats:
    """Snapshot current host CPU / memory / disk usage.

    ``psutil.cpu_percent(interval=X)`` blocks for X seconds sampling. For
    a once-a-day digest this is fine; tests pass a smaller interval.
    Disk anchor differs per OS — root on POSIX, C:\\ on Windows.
    """
    cpu = psutil.cpu_percent(interval=cpu_interval_s)
    memory = psutil.virtual_memory().percent
    disk_path = "C:\\" if sys.platform.startswith("win") else "/"
    disk = psutil.disk_usage(disk_path).percent
    return HostStats(
        cpu_pct=float(cpu),
        memory_pct=float(memory),
        disk_pct=float(disk),
    )


# ------------------------------------------------------------------ adapter health


_OLLAMA_SLOW_MS = 1000
_ANTHROPIC_SLOW_MS = 1500


async def gather_adapter_health(
    *,
    ollama_url: str,
    anthropic_url: str,
    anthropic_api_key: str | None,
    timeout_s: float = 5.0,
    client: httpx.AsyncClient | None = None,
) -> AdapterHealth:
    """Probe both LLM adapters concurrently.

    Independent probes; ``asyncio.gather`` runs them in parallel. Callers
    may inject an ``httpx.AsyncClient`` (for tests, or to reuse a
    connection pool); otherwise a fresh short-lived client is created
    and closed here.
    """
    owned_client = False
    if client is None:
        client = httpx.AsyncClient(timeout=timeout_s)
        owned_client = True
    try:
        ollama, anthropic = await asyncio.gather(
            _probe_ollama(client, ollama_url),
            _probe_anthropic(client, anthropic_url, anthropic_api_key),
        )
    finally:
        if owned_client:
            await client.aclose()
    return AdapterHealth(ollama=ollama, anthropic=anthropic)


async def _probe_ollama(client: httpx.AsyncClient, url: str) -> ProbeResult:
    endpoint = url.rstrip("/") + "/api/tags"
    start = time.perf_counter()
    try:
        resp = await client.get(endpoint)
    except httpx.RequestError as exc:
        return ProbeResult("red", f"unreachable: {type(exc).__name__}", None)
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    if resp.status_code == 200:
        if elapsed_ms < _OLLAMA_SLOW_MS:
            return ProbeResult("green", None, elapsed_ms)
        return ProbeResult("yellow", f"slow: {elapsed_ms}ms", elapsed_ms)
    return ProbeResult("red", f"HTTP {resp.status_code}", elapsed_ms)


async def _probe_anthropic(
    client: httpx.AsyncClient, url: str, api_key: str | None
) -> ProbeResult:
    if not api_key:
        return ProbeResult("yellow", "no api key configured", None)
    endpoint = url.rstrip("/") + "/v1/models"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    start = time.perf_counter()
    try:
        resp = await client.get(endpoint, headers=headers)
    except httpx.RequestError as exc:
        return ProbeResult("red", f"unreachable: {type(exc).__name__}", None)
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    if resp.status_code == 200:
        if elapsed_ms < _ANTHROPIC_SLOW_MS:
            return ProbeResult("green", None, elapsed_ms)
        return ProbeResult("yellow", f"slow: {elapsed_ms}ms", elapsed_ms)
    if resp.status_code == 401:
        return ProbeResult("red", "HTTP 401 — api key rejected", elapsed_ms)
    return ProbeResult("red", f"HTTP {resp.status_code}", elapsed_ms)


# ------------------------------------------------------------------ hardening


def load_hardening_status(path: Path) -> dict:
    """Read the hardening seed file. Loud on missing/malformed.

    Missing seed is an installation error, not a runtime edge case — the
    digest cannot report "hardening" state without ground truth. Prefer
    failing loudly at 06:30 than silently green'ing a broken install.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"hardening seed file not found: {path} — "
            "expected data/seed/hardening_status.json (install incomplete?)"
        )
    with path.open("r", encoding="utf-8") as fh:
        try:
            data = json.load(fh)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"hardening seed file is not valid JSON: {path} — {exc}"
            ) from exc
    controls = data.get("controls") if isinstance(data, dict) else None
    if not isinstance(controls, list):
        raise ValueError(
            f"hardening seed missing 'controls' array: {path}"
        )
    return data


# ------------------------------------------------------------------ log parse


# Matches the Python logging default asctime shape "YYYY-MM-DD HH:MM:SS,mmm".
_TIMESTAMP_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}),(\d{3})")

# The exact strings emitted by the L2 modules. Re-verified against
# app/L2_guardrails/{baa_gate,phi_redactor,injection_sentinel}.py at author
# time — if those log messages change, these regexes must move with them.
# See ADR-0008 §7 for the intent.
_BAA_DENY_RE = re.compile(r"\bbaa_gate_decision\s+decision=deny\b")
_PHI_REDACT_RE = re.compile(r"\bphi_scan\s+phi_present=True\s+phi_tier=(T[123])\b")
_INJ_DENY_RE = re.compile(r"\binjection_sentinel_decision\s+decision=deny\b")
_INJ_FLAG_RE = re.compile(r"\binjection_sentinel_decision\s+decision=flag\b")


def gather_guardrail_activity_24h(
    log_path: Path,
    now: datetime,
    window_hours: int = 24,
) -> GuardrailActivity:
    """Count L2 decision lines in the last ``window_hours``.

    Missing file → all-zeros (fresh install has no activity to report).
    Malformed lines (bad timestamp, unrecognised shape) are skipped and
    the count is exposed via ``lines_skipped`` for observability. Only
    lines within the rolling window contribute to the counts.

    Timezone contract: ``now`` and the log timestamps are assumed to be
    in the same reference. Python's default logging writes local naive
    time; the agent passes ``datetime.now()`` (naive local). If ``now``
    is tz-aware, parsed timestamps are aligned to its tz — a rough
    approximation, but 24h drift-tolerance covers any real offset.
    """
    zero_by_tier = {"T1": 0, "T2": 0, "T3": 0}

    if not log_path.exists():
        return GuardrailActivity(
            phi_redactions_total=0,
            phi_redactions_by_tier=zero_by_tier,
            baa_blocks=0,
            injection_blocks=0,
            injection_flags=0,
            lines_parsed=0,
            lines_skipped=0,
        )

    cutoff = now - timedelta(hours=window_hours)
    phi_by_tier = {"T1": 0, "T2": 0, "T3": 0}
    baa_blocks = 0
    injection_blocks = 0
    injection_flags = 0
    lines_parsed = 0
    lines_skipped = 0

    with log_path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            ts_match = _TIMESTAMP_RE.match(line)
            if ts_match is None:
                lines_skipped += 1
                continue
            try:
                ts = datetime.strptime(ts_match.group(1), "%Y-%m-%d %H:%M:%S")
            except ValueError:
                lines_skipped += 1
                continue
            ts = ts.replace(microsecond=int(ts_match.group(2)) * 1000)
            if now.tzinfo is not None:
                ts = ts.replace(tzinfo=now.tzinfo)
            if ts < cutoff:
                continue
            lines_parsed += 1

            if _BAA_DENY_RE.search(line):
                baa_blocks += 1
                continue
            phi_hit = _PHI_REDACT_RE.search(line)
            if phi_hit is not None:
                phi_by_tier[phi_hit.group(1)] += 1
                continue
            if _INJ_DENY_RE.search(line):
                injection_blocks += 1
                continue
            if _INJ_FLAG_RE.search(line):
                injection_flags += 1

    _logger.info(
        "guardrail_activity_parsed path=%s window_h=%d "
        "parsed=%d skipped=%d phi_total=%d baa_blocks=%d "
        "injection_blocks=%d injection_flags=%d",
        log_path,
        window_hours,
        lines_parsed,
        lines_skipped,
        sum(phi_by_tier.values()),
        baa_blocks,
        injection_blocks,
        injection_flags,
    )
    return GuardrailActivity(
        phi_redactions_total=sum(phi_by_tier.values()),
        phi_redactions_by_tier=phi_by_tier,
        baa_blocks=baa_blocks,
        injection_blocks=injection_blocks,
        injection_flags=injection_flags,
        lines_parsed=lines_parsed,
        lines_skipped=lines_skipped,
    )
