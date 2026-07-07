"""FastAPI entrypoint for the SignalCare Agentic Demo.

Wires up all architectural layers L0–L7. Every incoming request receives a
trace_id and flows through: L1 (API) -> L2 (Guardrails) -> L4 (Orchestrator) ->
L5 (Tools) -> L6 (Adapters) -> L7 (Stability Map / Local Impls).
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi import Path as FastAPIPath
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from L0_observability.prompt_registry import FileBackedPromptRegistry, PromptRenderer
from L2_guardrails import (
    BAAGateError,
    BAAGateGuard,
    InjectionSentinel,
    InjectionSentinelError,
    PHIRedactor,
)
from L3_agents.compliance_ops import ComplianceOpsAgent, DigestResult
from L6_adapters.ai_gateway import (
    AIGateway,
    AIGatewayError,
    CompletionRequest,
    Message,
    Tier,
    TieredAIGateway,
)

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def _configure_logging() -> None:
    """Attach stdout + rotating-file handlers to the root logger.

    Durable file at ``data/logs/signalcare.log`` is the source the L3
    compliance_ops digest tool greps for guardrail activity counts (see
    ADR-0008 §7). Rotates at 10MB with 3 backups so a runaway loop
    cannot silently fill the disk. Directory is created if missing —
    fresh installs boot cleanly with an empty log.
    """
    repo_root = Path(__file__).resolve().parent.parent
    log_dir = repo_root / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "signalcare.log"
    handlers: list[logging.Handler] = [
        logging.StreamHandler(),
        RotatingFileHandler(
            log_path,
            maxBytes=10 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        ),
    ]
    logging.basicConfig(level=logging.INFO, format=_LOG_FORMAT, handlers=handlers)


_configure_logging()
logger = logging.getLogger("signalcare")


_DIGEST_DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"
_DIGEST_JOB_ID = "compliance_ops_daily_digest"


def _resolve_digest_tz() -> ZoneInfo:
    """Read DIGEST_TZ, fall back to UTC on unknown zone.

    ADR-0008 §8 pins the trigger at 06:30 in DIGEST_TZ (Prav's local is
    America/New_York; default UTC). Bad env value must not prevent boot —
    fail-open to UTC with a WARN. Same shape as the sentinel classifier's
    fail-open error path.
    """
    name = os.getenv("DIGEST_TZ", "UTC")
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        logger.warning("digest_tz_invalid requested=%s fallback=UTC", name)
        return ZoneInfo("UTC")


def _ondemand_digest_allowed() -> bool:
    """Env-gate for POST /digest/generate. Read on every call, not cached.

    Default false per ADR-0008 §2 — the endpoint is a dev/demo affordance.
    Re-reading env each call means flipping the flag doesn't need a restart
    during a demo session.
    """
    return os.getenv("ALLOW_ONDEMAND_DIGEST", "false").strip().lower() in {
        "true",
        "1",
        "yes",
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown hooks — initialize adapters, tear them down cleanly."""
    logger.info("SignalCare Agentic Demo starting")
    # L6: concrete AI Gateway router (see ADR-0003, ADR-0004).
    tiered = TieredAIGateway()
    # L2: BAA gate — reads phi_present, blocks unapproved-vendor + PHI (rule 3).
    # ADR-0005: guard wraps the router, not individual adapters.
    gated = BAAGateGuard(tiered)
    # L2: PHI redactor — scans content, tags phi_present + phi_tier, redacts per
    # REDACTION_MODE. Runs before the gate so the gate has the flag (ADR-0006).
    redacted = PHIRedactor(gated)
    # L2: Injection sentinel — outermost, runs first. Regex-first, LLM fallback
    # for suspicion-flagged content. Classifier gateway is the gate-wrapped
    # router (skipping the redactor and the sentinel itself) so that
    # (a) no recursion, (b) classifier sees raw content, (c) BAA gate still
    # applies to the classifier's own LLM call. See ADR-0007.
    app.state.ai_gateway = InjectionSentinel(redacted, classifier=gated)
    # L0: prompt registry — YAML source of truth (Phase 2 per ADR-0009).
    # One directory walk at startup; every agent reads via
    # ``app.state.prompt_registry.get(key)``. Postgres runtime table lands in
    # Phase 3 as an additive same-interface swap. Path anchors are relative
    # to this file so the resolution is CWD-independent (uvicorn is launched
    # with CWD=app/, tests import via pytest.ini pythonpath=app).
    app_root = Path(__file__).resolve().parent
    repo_root = app_root.parent
    app.state.prompt_registry = FileBackedPromptRegistry(
        prompts_dir=app_root / "L0_observability" / "prompts",
        state_file=repo_root / "data" / "prompt_registry_state.json",
    )
    # L3: compliance_ops digest agent (see ADR-0008). CONSUMES the L2-wrapped
    # gateway via app.state.ai_gateway — L3 agents do not add guardrails.
    # Path anchors are repo_root-relative, matching the tools layer's
    # expectations (rotating log at data/logs/signalcare.log, hardening seed
    # at data/seed/hardening_status.json, output at data/digests/).
    digests_dir = repo_root / "data" / "digests"
    app.state.digests_dir = digests_dir
    app.state.digest_agent = ComplianceOpsAgent(
        gateway=app.state.ai_gateway,
        registry=app.state.prompt_registry,
        renderer=PromptRenderer(),
        digests_dir=digests_dir,
        log_path=repo_root / "data" / "logs" / "signalcare.log",
        hardening_path=repo_root / "data" / "seed" / "hardening_status.json",
        ollama_url=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
    )
    # L3 cron trigger — apscheduler on the same asyncio loop as FastAPI so
    # no thread hand-off. 30-minute grace so a boot delay at 06:31 still
    # fires the day's run. shutdown(wait=False) at teardown cancels the
    # in-flight job cleanly. See ADR-0008 §2, §8.
    digest_tz = _resolve_digest_tz()
    app.state.digest_tz = digest_tz
    scheduler = AsyncIOScheduler(timezone=digest_tz)
    scheduler.add_job(
        app.state.digest_agent.run_daily,
        CronTrigger(hour=6, minute=30, timezone=digest_tz),
        id=_DIGEST_JOB_ID,
        replace_existing=True,
        misfire_grace_time=60 * 30,
    )
    scheduler.start()
    app.state.scheduler = scheduler
    next_run = scheduler.get_job(_DIGEST_JOB_ID).next_run_time
    logger.info(
        "compliance_ops_scheduler_started tz=%s next_run=%s ondemand=%s",
        digest_tz.key,
        next_run.isoformat() if next_run else "unscheduled",
        _ondemand_digest_allowed(),
    )
    # TODO Week 3: initialize identity/relational/object/event/secrets/telemetry adapters
    # TODO Week 3: start L4 orchestrator background workers
    yield
    logger.info("SignalCare Agentic Demo shutting down")
    if hasattr(app.state, "scheduler"):
        app.state.scheduler.shutdown(wait=False)
    await app.state.ai_gateway.close()


app = FastAPI(
    title="SignalCare Agentic Demo",
    description="Cloud-agnostic agentic architecture reference implementation",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Admin UI
    allow_methods=["*"],
    allow_headers=["*"],
)


# TODO Week 3: attach OpenTelemetry instrumentation
# TODO Week 3: mount L1 review UX routers
# TODO Week 4-7: mount agent routers


@app.exception_handler(BAAGateError)
async def baa_gate_error_handler(request: Request, exc: BAAGateError) -> JSONResponse:
    """Map BAA gate denials to HTTP 451 (Unavailable For Legal Reasons, RFC 7725).

    Distinct from AIGatewayError (502) — a BAA denial is a policy decision the caller
    must never bypass, whereas an AIGatewayError is a transient issue callers may
    retry. See ADR-0005.
    """
    logger.warning(
        "baa_gate_blocked vendor=%s trace_id=%s path=%s",
        exc.vendor,
        exc.trace_id,
        request.url.path,
    )
    return JSONResponse(
        status_code=451,
        content={
            "error": "BAA required",
            "detail": (
                f"Vendor '{exc.vendor}' is not in APPROVED_PHI_VENDORS. Request "
                "blocked by L2 BAA gate."
            ),
            "vendor": exc.vendor,
            "trace_id": exc.trace_id,
        },
    )


@app.exception_handler(InjectionSentinelError)
async def injection_sentinel_error_handler(
    request: Request, exc: InjectionSentinelError
) -> JSONResponse:
    """Map injection sentinel blocks to HTTP 400 (Bad Request).

    The malformed component is the request content itself (adversarial input).
    Detail is deliberately terse to avoid leaking the pattern set to a probing
    attacker — internal detail (source, pattern) stays in the audit log,
    keyed by trace_id. Distinct from BAAGateError (451) and AIGatewayError
    (502). See ADR-0007.
    """
    logger.warning(
        "injection_sentinel_blocked source=%s pattern=%s trace_id=%s path=%s",
        exc.source,
        exc.pattern,
        exc.trace_id,
        request.url.path,
    )
    return JSONResponse(
        status_code=400,
        content={
            "error": "Request blocked",
            "detail": "Message content flagged by L2 injection sentinel.",
            "trace_id": exc.trace_id,
        },
    )


@app.get("/health")
async def health() -> dict:
    """Basic liveness check."""
    return {"status": "ok", "service": "signalcare-agentic-demo", "version": "0.1.0"}


@app.get("/")
async def root() -> dict:
    """Root endpoint returns architecture summary."""
    return {
        "name": "SignalCare Agentic Demo",
        "purpose": "Cloud-agnostic agentic architecture reference implementation",
        "layers": {
            "L0": "Observability, Evals, Feedback",
            "L1": "Human Review UX",
            "L2": "Guardrails & Policy",
            "L2A": "Memory & Context Fabric",
            "L2B": "Evidence Fabric",
            "L2C": "Hybrid Retrieval / RAG",
            "L3": "Specialist Agents (5 core + 3 stubs)",
            "L4": "Multi-Agent Orchestrator",
            "L5": "Agent Tool Layer",
            "L6": "Cloud-Agnostic Adapters (8)",
            "L7": "Stability Map (local implementations)",
        },
        "docs": "/docs",
        "arch": "See ARCHITECTURE.md",
    }


# ---------------------------------------------------------------------------
# /agents/echo — Week 1 hello-world proof-of-work for the AI Gateway adapter.
#
# Given a tier and a prompt, dispatches through the L2-guarded AI Gateway
# (BAAGateGuard wrapping TieredAIGateway) to either Ollama (Fast) or Anthropic
# (Balanced/Reasoning per ADR-0004) and returns the response with provider +
# model + latency + token counts. The caller never learns which concrete
# adapter served the request other than via the reported metadata — which is
# exactly the abstraction claim from ADR-0002. If BAA policy denies the vendor,
# the guard raises BAAGateError → HTTP 451 (see ADR-0005).
# ---------------------------------------------------------------------------


class EchoRequest(BaseModel):
    tier: Literal["fast", "balanced", "reasoning"] = Field(
        default="fast",
        description="Model tier. 'fast'->Ollama; 'balanced'/'reasoning'->Anthropic (ADR-0004).",
    )
    prompt: str = Field(..., min_length=1, description="User message to echo through the LLM.")
    system: str | None = Field(
        default=None,
        description="Optional system prompt. Defaults to a terse assistant persona.",
    )
    max_tokens: int = Field(default=256, ge=1, le=4096)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)


class EchoResponse(BaseModel):
    text: str
    provider: str
    model: str
    tier: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    trace_id: str


@app.post("/agents/echo", response_model=EchoResponse)
async def agents_echo(payload: EchoRequest, request: Request) -> EchoResponse:
    """Round-trip a prompt through the AI Gateway. Week 1 architectural proof-point.

    trace_id propagates through the adapter into the response for debuggability. Once L4
    orchestrator lands (Phase 3), this endpoint will move behind it; for now it's a direct
    dispatch to make the adapter behavior easy to verify.
    """
    trace_id = request.headers.get("x-trace-id") or f"echo-{uuid.uuid4().hex[:12]}"

    system = payload.system or "You are a concise assistant. Reply in one short sentence."
    req = CompletionRequest(
        tier=Tier(payload.tier),
        messages=[
            Message(role="system", content=system),
            Message(role="user", content=payload.prompt),
        ],
        max_tokens=payload.max_tokens,
        temperature=payload.temperature,
        trace_id=trace_id,
    )

    # Typed as the abstract AIGateway — could be a raw router or wrapped in guardrails.
    # The BAA gate raises BAAGateError, handled by the app-level 451 exception handler
    # above (does NOT fall into this except AIGatewayError block by design; see ADR-0005).
    gateway: AIGateway = request.app.state.ai_gateway
    try:
        result = await gateway.complete(req)
    except AIGatewayError as exc:
        logger.warning("ai_gateway_error tier=%s trace_id=%s err=%s", payload.tier, trace_id, exc)
        raise HTTPException(status_code=502, detail=f"AI Gateway error: {exc}") from exc

    logger.info(
        "ai_gateway_call tier=%s provider=%s model=%s latency_ms=%d tokens_in=%d tokens_out=%d trace_id=%s",
        payload.tier,
        result.provider,
        result.model,
        result.latency_ms,
        result.tokens_in,
        result.tokens_out,
        trace_id,
    )

    return EchoResponse(
        text=result.text,
        provider=result.provider,
        model=result.model,
        tier=payload.tier,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        latency_ms=result.latency_ms,
        trace_id=trace_id,
    )


# ---------------------------------------------------------------------------
# /digest/* — Phase 2 Compliance/Ops Founder Mode digest surface (ADR-0008 §2).
#
# Read paths (GET) serve pre-generated files from data/digests/ — the cron
# job at 06:30 in DIGEST_TZ produces YYYY-MM-DD.{json,md}. Never generate
# on-the-fly during a GET; a 404 means "the cron hasn't run yet today".
#
# Write path (POST) is env-gated by ALLOW_ONDEMAND_DIGEST (default false).
# Intended for demos and manual triggers, not production. The env-gate is
# re-read each call so a demo operator can flip the flag without restart.
# ---------------------------------------------------------------------------


class DigestGenerateResponse(BaseModel):
    """Return shape for POST /digest/generate.

    Paths are stringified so callers on any platform get the same shape;
    the admin UI (C-frontend session) fetches ``date`` and follows up with
    GET /digest/{date}/markdown for content.
    """

    date: str
    json_path: str
    markdown_path: str
    caps_triggered: dict[str, int]
    guardrail_overrides: bool


def _today_str_in_digest_tz(request: Request) -> str:
    """Return today's YYYY-MM-DD in the scheduler's timezone.

    A raw ``datetime.now()`` would resolve "today" in the server's local
    time — wrong if the server is UTC and DIGEST_TZ is America/New_York.
    Matching the tz the cron fires in guarantees /digest/today resolves
    to the same file the cron just wrote at 06:30.
    """
    tz = getattr(request.app.state, "digest_tz", None) or ZoneInfo("UTC")
    return datetime.now(tz).strftime("%Y-%m-%d")


def _read_digest_json(digests_dir: Path, date_str: str) -> dict:
    path = digests_dir / f"{date_str}.json"
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"no digest generated for {date_str}",
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("digest_read_error date=%s kind=json err=%s", date_str, exc)
        raise HTTPException(status_code=500, detail=f"digest read failed: {exc}") from exc


def _read_digest_markdown(digests_dir: Path, date_str: str) -> str:
    path = digests_dir / f"{date_str}.md"
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"no digest markdown for {date_str}",
        )
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("digest_read_error date=%s kind=md err=%s", date_str, exc)
        raise HTTPException(status_code=500, detail=f"digest read failed: {exc}") from exc


digest_router = APIRouter(prefix="/digest", tags=["digest"])


# Route ordering matters — `/today` and `/today/markdown` must be declared
# BEFORE `/{date_str}` so FastAPI resolves the literal path first. The date
# pattern would reject "today" anyway, but declaration order makes the
# routing table's intent explicit.


@digest_router.get("/today")
async def digest_today(request: Request) -> dict:
    """Return today's digest as JSON. 404 if the cron hasn't produced it yet."""
    date_str = _today_str_in_digest_tz(request)
    return _read_digest_json(request.app.state.digests_dir, date_str)


@digest_router.get("/today/markdown", response_class=Response)
async def digest_today_markdown(request: Request) -> Response:
    """Return today's digest as rendered markdown (text/markdown)."""
    date_str = _today_str_in_digest_tz(request)
    body = _read_digest_markdown(request.app.state.digests_dir, date_str)
    return Response(content=body, media_type="text/markdown; charset=utf-8")


@digest_router.get("/{date_str}")
async def digest_by_date(
    request: Request,
    date_str: str = FastAPIPath(..., pattern=_DIGEST_DATE_PATTERN, examples=["2026-07-07"]),
) -> dict:
    """Return the digest JSON for a specific historical date."""
    return _read_digest_json(request.app.state.digests_dir, date_str)


@digest_router.get("/{date_str}/markdown", response_class=Response)
async def digest_by_date_markdown(
    request: Request,
    date_str: str = FastAPIPath(..., pattern=_DIGEST_DATE_PATTERN, examples=["2026-07-07"]),
) -> Response:
    """Return the digest markdown for a specific historical date."""
    body = _read_digest_markdown(request.app.state.digests_dir, date_str)
    return Response(content=body, media_type="text/markdown; charset=utf-8")


@digest_router.post("/generate", response_model=DigestGenerateResponse)
async def digest_generate(request: Request) -> DigestGenerateResponse:
    """Regenerate today's digest immediately. Env-gated by ALLOW_ONDEMAND_DIGEST.

    Same-day reruns overwrite. Live Anthropic call — cost is pennies per
    run at Balanced tier / 1200 max_tokens; this is the surface `make
    demo-digest` hits to prove the L1→L2→L6 stack end-to-end.
    """
    if not _ondemand_digest_allowed():
        raise HTTPException(
            status_code=403,
            detail=(
                "on-demand digest is disabled; set ALLOW_ONDEMAND_DIGEST=true "
                "to enable (dev/demo only — see ADR-0008 §2)"
            ),
        )
    trace_id = request.headers.get("x-trace-id") or f"digest-ondemand-{uuid.uuid4().hex[:12]}"
    logger.info("digest_generate_ondemand_start trace_id=%s", trace_id)
    agent: ComplianceOpsAgent = request.app.state.digest_agent
    try:
        result: DigestResult = await agent.run_daily()
    except Exception as exc:
        logger.exception("digest_generate_ondemand_failed trace_id=%s", trace_id)
        raise HTTPException(status_code=500, detail=f"digest generation failed: {exc}") from exc
    logger.info(
        "digest_generate_ondemand_complete trace_id=%s date=%s caps=%s overrides=%s",
        trace_id, result.date, result.caps_triggered, result.guardrail_overrides,
    )
    return DigestGenerateResponse(
        date=result.date,
        json_path=str(result.json_path),
        markdown_path=str(result.markdown_path),
        caps_triggered=result.caps_triggered,
        guardrail_overrides=result.guardrail_overrides,
    )


app.include_router(digest_router)
