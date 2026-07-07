"""FastAPI entrypoint for the SignalCare Agentic Demo.

Wires up all architectural layers L0–L7. Every incoming request receives a
trace_id and flows through: L1 (API) -> L2 (Guardrails) -> L4 (Orchestrator) ->
L5 (Tools) -> L6 (Adapters) -> L7 (Stability Map / Local Impls).
"""
from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from L6_adapters.ai_gateway import (
    AIGatewayError,
    CompletionRequest,
    Message,
    Tier,
    TieredAIGateway,
)

logger = logging.getLogger("signalcare")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown hooks — initialize adapters, tear them down cleanly."""
    logger.info("SignalCare Agentic Demo starting")
    # AI Gateway is the only Week 1 adapter (see ADR-0003).
    # Construction can fail if OPENROUTER_API_KEY is missing — surface loudly at startup.
    app.state.ai_gateway = TieredAIGateway()
    # TODO Week 2: initialize L2 guardrails (BAA gate, PHI redactor, injection sentinel)
    # TODO Week 3: initialize identity/relational/object/event/secrets/telemetry adapters
    # TODO Week 3: start L4 orchestrator background workers
    # TODO Week 2: seed prompt registry from YAML sources
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


# TODO Week 2: attach L2 guardrail middleware here (BAA gate, injection sentinel, redactor)
# TODO Week 3: attach OpenTelemetry instrumentation
# TODO Week 3: mount L1 review UX routers
# TODO Week 4-7: mount agent routers


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
# Given a tier and a prompt, dispatches through the TieredAIGateway to either
# Ollama (Fast) or OpenRouter (Balanced/Reasoning) and returns the response
# with provider + model + latency + token counts. The caller never learns
# which concrete adapter served the request other than via the reported
# metadata — which is exactly the abstraction claim from ADR-0002.
# ---------------------------------------------------------------------------


class EchoRequest(BaseModel):
    tier: Literal["fast", "balanced", "reasoning"] = Field(
        default="fast",
        description="Model tier. 'fast'->Ollama; 'balanced'/'reasoning'->OpenRouter.",
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

    gateway: TieredAIGateway = request.app.state.ai_gateway
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
