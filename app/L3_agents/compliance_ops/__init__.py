"""L3 · Compliance/Ops — Founder Mode daily digest agent.

The first L3 agent to ship. Deliberately non-PHI so it exercises the
L2 stack, the L0 prompt registry, and the L6 gateway without needing
the L2B evidence fabric or the L4 orchestrator to land first. See
ADR-0008 (UX spec) and the module docstring in ``agent.py``.
"""
from .agent import ComplianceOpsAgent, DigestResult
from .renderer import render_markdown

__all__ = [
    "ComplianceOpsAgent",
    "DigestResult",
    "render_markdown",
]
