"""Prompt renderer — bind a ``PromptDefinition`` to actual placeholder values.

The renderer is a separate concern from the registry per ADR-0009 §6.
Given a definition + a set of caller-supplied values, it returns
``(system, user)`` strings ready for the AI Gateway.

One placeholder is auto-computed: ``output_schema_inline``. If it appears
in ``definition.placeholders`` the renderer supplies
``json.dumps(definition.output_schema, indent=2)`` for it and callers
MUST NOT pass it themselves. Every other placeholder is caller-supplied.

Failure modes are loud, not silent:
    - Missing placeholder → ``PromptRenderError``
    - Extra placeholder → ``PromptRenderError``
    - Caller supplied ``output_schema_inline`` themselves → ``PromptRenderError``
    - ``str.format_map`` internal failure (unbalanced braces in template) →
      ``PromptRenderError`` chained from the underlying exception.

Schema validation of the LLM's response is a separate downstream concern
and is intentionally NOT in the renderer's contract.
"""
from __future__ import annotations

import json

from .types import PromptDefinition

_AUTO_PLACEHOLDER = "output_schema_inline"


class PromptRenderError(Exception):
    """Renderer refused the call — missing, extra, or auto-conflict placeholder."""


class PromptRenderer:
    """Stateless renderer. Kept as a class for symmetry with future variants
    (e.g. an Anthropic ``tool_use`` renderer or a renderer that injects
    ``trace_id``). Instantiate once at startup or per call — both are fine.
    """

    def render(
        self, definition: PromptDefinition, /, **values: object
    ) -> tuple[str, str]:
        """Return ``(system, user)`` strings ready for the AI Gateway."""
        expected = set(definition.placeholders)
        provides_schema = _AUTO_PLACEHOLDER in expected
        supplied = set(values.keys())

        if provides_schema and _AUTO_PLACEHOLDER in supplied:
            raise PromptRenderError(
                f"caller must not supply {_AUTO_PLACEHOLDER!r} for prompt "
                f"{definition.id!r} — renderer computes it from definition.output_schema"
            )

        caller_expected = expected - ({_AUTO_PLACEHOLDER} if provides_schema else set())
        missing = caller_expected - supplied
        extra = supplied - caller_expected
        if missing or extra:
            raise PromptRenderError(
                f"placeholder mismatch for {definition.id!r}: "
                f"missing={sorted(missing)} extra={sorted(extra)}"
            )

        substitutions: dict[str, object] = dict(values)
        if provides_schema:
            substitutions[_AUTO_PLACEHOLDER] = json.dumps(
                definition.output_schema, indent=2
            )

        try:
            rendered_user = definition.user_template.format_map(substitutions)
        except (KeyError, IndexError) as exc:
            raise PromptRenderError(
                f"format_map failed for {definition.id!r}: {exc}"
            ) from exc

        return definition.system, rendered_user
