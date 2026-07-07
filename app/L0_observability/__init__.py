"""L0 — Observability, Evals, Feedback.

Phase 2 sub-packages:
    - prompt_registry — YAML-first prompt storage (ADR-0009). Phase 3 adds
      a Postgres-backed implementation with the same interface.
    - prompts/ — YAML source of truth. Not a Python package; loaded at
      startup by ``FileBackedPromptRegistry`` walking ``*.yaml``.

Phase 3+ sub-packages (not yet implemented): evals, feedback,
telemetry-collector wiring.
"""
