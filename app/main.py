"""FastAPI entrypoint for the SignalCare Agentic Demo.

Wires up all architectural layers L0–L7. Every incoming request receives a
trace_id and flows through: L1 (API) -> L2 (Guardrails) -> L4 (Orchestrator) ->
L5 (Tools) -> L6 (Adapters) -> L7 (Stability Map / Local Impls).
"""
from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from L0_observability.prompt_registry import FileBackedPromptRegistry
from L2_guardrails import (
    BAAGateError,
    BAAGateGuard,
    InjectionSentinel,
    InjectionSentinelError,
    PHIRedactor,
)
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
    # TODO Week 3: initialize identity/relational/object/event/secrets/telemetry adapters
    # TODO Week 3: start L4 orchestrator background workers
    yield
    logger.info("SignalCare Agentic Demo shutting down")
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
