"""Integration tests for /digest/* endpoints (ADR-0008 §2, Phase 2 CLOSE).

Endpoint contract is exercised via FastAPI TestClient against a fresh
FastAPI app that mounts only ``digest_router`` from ``main``. This
avoids booting main.lifespan (which starts the scheduler and constructs
the real L2/L6 gateway stack); we instead populate ``app.state`` by
hand with a tmp_path digests dir and a deterministic stub agent.

The live end-to-end path — cron trigger firing at 06:30, the real
Balanced-tier Anthropic call — is verified manually via
``make demo-digest`` per the Session C handoff.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from L3_agents.compliance_ops import DigestResult
from main import (
    _DIGEST_JOB_ID,
    _ondemand_digest_allowed,
    _resolve_digest_tz,
    digest_router,
)


# --------------------------------------------------------------------- helpers


@dataclass
class _StubAgent:
    """Deterministic agent stub.

    Writes today's files to the same shape ``ComplianceOpsAgent.run_daily``
    produces so downstream reads work uniformly. No LLM call, no probes,
    no log parsing. Behavior can be tuned per test via ``caps_triggered``
    and ``guardrail_overrides``.
    """

    digests_dir: Path
    date_str: str
    caps_triggered: dict[str, int] | None = None
    guardrail_overrides: bool = False

    async def run_daily(self, *, now: datetime | None = None) -> DigestResult:
        self.digests_dir.mkdir(parents=True, exist_ok=True)
        json_path = self.digests_dir / f"{self.date_str}.json"
        md_path = self.digests_dir / f"{self.date_str}.md"
        payload = {
            "date": self.date_str,
            "generated_at": "2026-07-07T06:30:00+00:00",
            "attention": [],
            "watch": [],
            "guardrails": {},
            "systems": [],
            "decisions": [],
        }
        json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        md_path.write_text(f"# stub digest {self.date_str}\n", encoding="utf-8")
        return DigestResult(
            date=self.date_str,
            json_path=json_path,
            markdown_path=md_path,
            caps_triggered=self.caps_triggered or {},
            guardrail_overrides=self.guardrail_overrides,
        )


def _build_test_app(
    digests_dir: Path,
    *,
    agent: object | None = None,
    tz: ZoneInfo | None = None,
) -> FastAPI:
    app = FastAPI()
    app.include_router(digest_router)
    app.state.digests_dir = digests_dir
    app.state.digest_tz = tz or ZoneInfo("UTC")
    app.state.digest_agent = agent
    return app


def _write_digest_pair(digests_dir: Path, date_str: str, payload: dict | None = None) -> None:
    digests_dir.mkdir(parents=True, exist_ok=True)
    body = payload or {"date": date_str, "attention": []}
    (digests_dir / f"{date_str}.json").write_text(json.dumps(body), encoding="utf-8")
    (digests_dir / f"{date_str}.md").write_text(f"# md {date_str}\n", encoding="utf-8")


def _today_utc() -> str:
    return datetime.now(ZoneInfo("UTC")).strftime("%Y-%m-%d")


# --------------------------------------------------------------------- GET /digest/today


def test_digest_today_returns_json_when_file_exists(tmp_path):
    date_str = _today_utc()
    _write_digest_pair(tmp_path, date_str, {"date": date_str, "attention": []})
    client = TestClient(_build_test_app(tmp_path))

    resp = client.get("/digest/today")

    assert resp.status_code == 200
    assert resp.json()["date"] == date_str


def test_digest_today_returns_404_when_missing(tmp_path):
    client = TestClient(_build_test_app(tmp_path))

    resp = client.get("/digest/today")

    assert resp.status_code == 404
    assert "no digest generated" in resp.json()["detail"]


def test_digest_today_markdown_returns_text(tmp_path):
    date_str = _today_utc()
    _write_digest_pair(tmp_path, date_str)
    client = TestClient(_build_test_app(tmp_path))

    resp = client.get("/digest/today/markdown")

    assert resp.status_code == 200
    assert "text/markdown" in resp.headers["content-type"]
    assert f"# md {date_str}" in resp.text


def test_digest_today_markdown_404_when_missing(tmp_path):
    client = TestClient(_build_test_app(tmp_path))

    resp = client.get("/digest/today/markdown")

    assert resp.status_code == 404


def test_digest_today_respects_configured_tz(tmp_path):
    """/today resolves to the DIGEST_TZ date, not the server's local date.

    Only observable when the tz shift crosses a day boundary — hard to
    force portably, so we test that the file the endpoint reads matches
    the tz-aware "today" string exactly.
    """
    tz = ZoneInfo("America/New_York")
    date_str = datetime.now(tz).strftime("%Y-%m-%d")
    _write_digest_pair(tmp_path, date_str, {"date": date_str})
    client = TestClient(_build_test_app(tmp_path, tz=tz))

    resp = client.get("/digest/today")

    assert resp.status_code == 200
    assert resp.json()["date"] == date_str


# --------------------------------------------------------------------- GET /digest/{date_str}


def test_digest_by_date_returns_json(tmp_path):
    _write_digest_pair(tmp_path, "2026-01-15", {"date": "2026-01-15", "attention": []})
    client = TestClient(_build_test_app(tmp_path))

    resp = client.get("/digest/2026-01-15")

    assert resp.status_code == 200
    assert resp.json()["date"] == "2026-01-15"


def test_digest_by_date_returns_404_for_missing(tmp_path):
    client = TestClient(_build_test_app(tmp_path))

    resp = client.get("/digest/2020-01-01")

    assert resp.status_code == 404
    assert "no digest generated for 2020-01-01" in resp.json()["detail"]


def test_digest_by_date_markdown(tmp_path):
    _write_digest_pair(tmp_path, "2026-01-15")
    client = TestClient(_build_test_app(tmp_path))

    resp = client.get("/digest/2026-01-15/markdown")

    assert resp.status_code == 200
    assert "text/markdown" in resp.headers["content-type"]
    assert "# md 2026-01-15" in resp.text


@pytest.mark.parametrize(
    "bad_date",
    ["not-a-date", "2026-1-1", "26-01-01", "2026-01-15-extra", "20260715"],
)
def test_digest_by_date_rejects_bad_format(tmp_path, bad_date):
    """FastAPI's path pattern validation returns 422 on shape mismatch.

    URL-structure mismatches (a slash inside the date, e.g. ``2026/01/15``)
    are a different concern — they fail routing entirely, not pattern
    validation — and are exercised by the generic 404 test.
    """
    client = TestClient(_build_test_app(tmp_path))

    resp = client.get(f"/digest/{bad_date}")

    assert resp.status_code == 422


# --------------------------------------------------------------------- POST /digest/generate — env-gate


def test_digest_generate_blocked_when_env_gate_disabled(tmp_path):
    agent = _StubAgent(digests_dir=tmp_path, date_str="2026-07-07")
    client = TestClient(_build_test_app(tmp_path, agent=agent))

    with patch.dict(os.environ, {"ALLOW_ONDEMAND_DIGEST": "false"}, clear=False):
        resp = client.post("/digest/generate")

    assert resp.status_code == 403
    assert "on-demand digest is disabled" in resp.json()["detail"]
    assert not (tmp_path / "2026-07-07.json").exists()  # agent not invoked


def test_digest_generate_missing_env_treated_as_disabled(tmp_path):
    agent = _StubAgent(digests_dir=tmp_path, date_str="2026-07-07")
    client = TestClient(_build_test_app(tmp_path, agent=agent))

    env = {k: v for k, v in os.environ.items() if k != "ALLOW_ONDEMAND_DIGEST"}
    with patch.dict(os.environ, env, clear=True):
        resp = client.post("/digest/generate")

    assert resp.status_code == 403


@pytest.mark.parametrize("value", ["true", "1", "yes", "TRUE", "Yes", "  true  "])
def test_digest_generate_accepts_truthy_env(tmp_path, value):
    agent = _StubAgent(digests_dir=tmp_path, date_str="2026-07-07")
    client = TestClient(_build_test_app(tmp_path, agent=agent))

    with patch.dict(os.environ, {"ALLOW_ONDEMAND_DIGEST": value}, clear=False):
        resp = client.post("/digest/generate")

    assert resp.status_code == 200
    body = resp.json()
    assert body["date"] == "2026-07-07"
    assert body["caps_triggered"] == {}
    assert body["guardrail_overrides"] is False


@pytest.mark.parametrize("value", ["false", "0", "no", "", "maybe", "off"])
def test_digest_generate_rejects_non_truthy_env(tmp_path, value):
    agent = _StubAgent(digests_dir=tmp_path, date_str="2026-07-07")
    client = TestClient(_build_test_app(tmp_path, agent=agent))

    with patch.dict(os.environ, {"ALLOW_ONDEMAND_DIGEST": value}, clear=False):
        resp = client.post("/digest/generate")

    assert resp.status_code == 403


# --------------------------------------------------------------------- POST /digest/generate — happy path


def test_digest_generate_persists_agent_result(tmp_path):
    agent = _StubAgent(
        digests_dir=tmp_path,
        date_str="2026-07-07",
        caps_triggered={"attention": 5},
        guardrail_overrides=True,
    )
    client = TestClient(_build_test_app(tmp_path, agent=agent))

    with patch.dict(os.environ, {"ALLOW_ONDEMAND_DIGEST": "true"}, clear=False):
        resp = client.post("/digest/generate")

    assert resp.status_code == 200
    body = resp.json()
    assert body["date"] == "2026-07-07"
    assert body["caps_triggered"] == {"attention": 5}
    assert body["guardrail_overrides"] is True
    assert (tmp_path / "2026-07-07.json").exists()
    assert (tmp_path / "2026-07-07.md").exists()


def test_digest_generate_agent_error_returns_500(tmp_path):
    class _FailingAgent:
        async def run_daily(self, *, now=None):
            raise RuntimeError("gateway is down")

    client = TestClient(_build_test_app(tmp_path, agent=_FailingAgent()))

    with patch.dict(os.environ, {"ALLOW_ONDEMAND_DIGEST": "true"}, clear=False):
        resp = client.post("/digest/generate")

    assert resp.status_code == 500
    assert "gateway is down" in resp.json()["detail"]


def test_digest_generate_propagates_trace_id_header(tmp_path, caplog):
    import logging

    agent = _StubAgent(digests_dir=tmp_path, date_str="2026-07-07")
    client = TestClient(_build_test_app(tmp_path, agent=agent))

    with patch.dict(os.environ, {"ALLOW_ONDEMAND_DIGEST": "true"}, clear=False):
        with caplog.at_level(logging.INFO, logger="signalcare"):
            resp = client.post(
                "/digest/generate", headers={"x-trace-id": "trace-abc-123"}
            )

    assert resp.status_code == 200
    # trace_id shows up in the structured info log for downstream correlation
    assert any("trace-abc-123" in rec.getMessage() for rec in caplog.records), \
        f"trace_id missing from logs; records: {[r.getMessage() for r in caplog.records]}"


# --------------------------------------------------------------------- lifespan helpers (unit-shaped, no ASGI boot)


def test_ondemand_digest_allowed_defaults_false(monkeypatch):
    monkeypatch.delenv("ALLOW_ONDEMAND_DIGEST", raising=False)
    assert _ondemand_digest_allowed() is False


@pytest.mark.parametrize("value", ["true", "1", "yes", "TRUE", "  Yes  "])
def test_ondemand_digest_allowed_truthy_values(monkeypatch, value):
    monkeypatch.setenv("ALLOW_ONDEMAND_DIGEST", value)
    assert _ondemand_digest_allowed() is True


@pytest.mark.parametrize("value", ["false", "0", "no", "off", "", "maybe"])
def test_ondemand_digest_allowed_falsy_values(monkeypatch, value):
    monkeypatch.setenv("ALLOW_ONDEMAND_DIGEST", value)
    assert _ondemand_digest_allowed() is False


def test_resolve_digest_tz_defaults_to_utc(monkeypatch):
    monkeypatch.delenv("DIGEST_TZ", raising=False)
    tz = _resolve_digest_tz()
    assert tz.key == "UTC"


def test_resolve_digest_tz_reads_env(monkeypatch):
    monkeypatch.setenv("DIGEST_TZ", "America/New_York")
    tz = _resolve_digest_tz()
    assert tz.key == "America/New_York"


def test_resolve_digest_tz_falls_back_on_invalid(monkeypatch):
    monkeypatch.setenv("DIGEST_TZ", "Definitely/Not/A/Real/Zone")
    tz = _resolve_digest_tz()
    assert tz.key == "UTC"


def test_digest_job_id_constant_stable():
    """The scheduler job ID is a public contract — a downstream admin
    tool (Phase 3+) may inspect it. Snapshot the constant."""
    assert _DIGEST_JOB_ID == "compliance_ops_daily_digest"
