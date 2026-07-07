"""Prompt registry — YAML-first storage for Phase 2 (Postgres additive in Phase 3).

Public surface. Depend on ``PromptRegistry`` (the protocol) in agent code;
wire ``FileBackedPromptRegistry`` in ``main.py`` lifespan. Renderer is a
separate concern — take a ``PromptDefinition`` from ``.get()`` and pass it
to ``PromptRenderer().render(definition, **values)``.

See ADR-0009 for design rationale.
"""
from .registry import (
    FileBackedPromptRegistry,
    PromptNotFoundError,
    PromptRegistry,
    PromptRegistryError,
    PromptSchemaError,
)
from .renderer import PromptRenderer, PromptRenderError
from .types import PromptDefinition

__all__ = [
    "FileBackedPromptRegistry",
    "PromptDefinition",
    "PromptNotFoundError",
    "PromptRegistry",
    "PromptRegistryError",
    "PromptRenderError",
    "PromptRenderer",
    "PromptSchemaError",
]
