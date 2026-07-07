"""Prompt-definition value type — one row of the registry.

Immutable dataclass. Identity is ``(id, hash)``. ``hash`` is
``sha256(yaml_file_bytes)[:12]`` — see ADR-0009 §4 for why content-hash
rather than semantic versioning.

The ``output_schema`` field is a Python dict (arbitrary JSON-schema-ish
shape) and is deliberately not frozen — freezing a dict in Python requires
either ``MappingProxyType`` or a tuple-of-tuples encoding, both of which
break natural authoring. ``@dataclass(frozen=True)`` still prevents field
reassignment on the instance; downstream code should treat ``output_schema``
as read-only by convention.
"""
from __future__ import annotations

from dataclasses import dataclass

from L6_adapters.ai_gateway import Tier


@dataclass(frozen=True)
class PromptDefinition:
    """One prompt as loaded from disk. See ADR-0009 §3 for the source schema."""

    id: str
    description: str
    owner: str
    tier: Tier
    max_tokens: int
    temperature: float
    system: str
    user_template: str
    placeholders: tuple[str, ...]
    output_schema: dict
    created_at: str
    notes: str | None
    hash: str
    source_file: str
