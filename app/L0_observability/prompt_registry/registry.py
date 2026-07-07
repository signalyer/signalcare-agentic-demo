"""Prompt registry — YAML-first storage for Phase 2 per ADR-0009.

Public surface
--------------
- ``PromptRegistry`` — the protocol every agent depends on.
- ``FileBackedPromptRegistry`` — the Phase 2 concrete implementation. Walks
  a directory of YAML files, validates their schema, computes content
  hashes, and logs drift against the previous startup's snapshot.
- Exceptions: ``PromptRegistryError`` (base), ``PromptSchemaError`` (loud
  boot-blocker on any schema violation), ``PromptNotFoundError``
  (agent asked for a key that isn't registered).

Phase 3 will ship a ``PostgresPromptRegistry`` in this same package with the
same interface. Wiring change lives in ``main.py`` lifespan; agent code
never touches. See ADR-0009 for the substrate-additive strategy.

Load-failure discipline
-----------------------
Startup fails loudly on any schema violation. A registry that silently
drops a broken prompt is worse than one that refuses to start — the agent
that expects the prompt would fail later with a less helpful message. See
ADR-0009 §5.
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import yaml

from L6_adapters.ai_gateway import Tier

from .snapshot import read_snapshot, write_snapshot
from .types import PromptDefinition

_logger = logging.getLogger("signalcare.prompt_registry")

# Match ``{name}`` where name is a valid Python identifier. Kept strict so
# incidental braces in prose (unlikely in a YAML prompt but not impossible)
# do not register as placeholders.
_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")

_REQUIRED_FIELDS: tuple[str, ...] = (
    "id",
    "description",
    "owner",
    "tier",
    "max_tokens",
    "temperature",
    "system",
    "user_template",
    "placeholders",
    "output_schema",
    "created_at",
    "notes",
)


class PromptRegistryError(Exception):
    """Base class for prompt-registry failures. Catch to catch all registry
    errors without conflating with rendering errors (``PromptRenderError``).
    """


class PromptSchemaError(PromptRegistryError):
    """A YAML file failed schema validation. See ADR-0009 §3 for the schema."""

    def __init__(self, source_file: str, reason: str):
        self.source_file = source_file
        self.reason = reason
        super().__init__(f"{source_file}: {reason}")


class PromptNotFoundError(PromptRegistryError):
    """Registry has no entry for the requested key."""

    def __init__(self, key: str, known: list[str]):
        self.key = key
        self.known = known
        known_str = ", ".join(known) if known else "none"
        super().__init__(f"prompt {key!r} not registered (known: {known_str})")


class PromptRegistry(Protocol):
    """Contract every registry substrate satisfies. See ADR-0009."""

    def get(self, key: str) -> PromptDefinition:
        """Return the prompt definition for ``key`` or raise ``PromptNotFoundError``."""

    def keys(self) -> list[str]:
        """Return the sorted list of registered prompt keys."""

    def all(self) -> dict[str, PromptDefinition]:
        """Return a shallow copy of ``{key: definition}``."""


class FileBackedPromptRegistry:
    """YAML source of truth + JSON drift-detection snapshot. No DB.

    Phase 2 substrate per ADR-0009. Wire once at startup; agents call
    ``.get(key)`` at call time. YAML edits require a restart — no hot
    reload in Phase 2. Phase 3's ``PostgresPromptRegistry`` will support
    hot reload.

    Constructor arguments:
        prompts_dir: Directory containing ``*.yaml`` prompt files. Every
            file is loaded on construction; nested subdirs are ignored.
        state_file: Path to the JSON drift-detection snapshot. Pass
            ``None`` to disable snapshotting (used in tests and in the
            rare case where the caller wants read-only startup).
    """

    def __init__(self, prompts_dir: Path, state_file: Path | None = None):
        self._prompts_dir = prompts_dir
        self._state_file = state_file
        self._prompts: dict[str, PromptDefinition] = {}
        self._load()

    def get(self, key: str) -> PromptDefinition:
        try:
            return self._prompts[key]
        except KeyError:
            raise PromptNotFoundError(key, sorted(self._prompts.keys())) from None

    def keys(self) -> list[str]:
        return sorted(self._prompts.keys())

    def all(self) -> dict[str, PromptDefinition]:
        return dict(self._prompts)

    # ------------------------------------------------------------------ private

    def _load(self) -> None:
        if not self._prompts_dir.exists():
            raise PromptRegistryError(
                f"prompts directory does not exist: {self._prompts_dir}"
            )
        prior = read_snapshot(self._state_file) if self._state_file else {}
        new_snapshot: dict[str, dict] = {}
        for yaml_path in sorted(self._prompts_dir.glob("*.yaml")):
            definition = self._load_one(yaml_path)
            self._prompts[definition.id] = definition
            prior_entry = prior.get(definition.id)
            if prior_entry is not None and prior_entry.get("prompt_hash") != definition.hash:
                _logger.warning(
                    "prompt_drift key=%s old_hash=%s new_hash=%s source=%s",
                    definition.id,
                    prior_entry.get("prompt_hash"),
                    definition.hash,
                    definition.source_file,
                )
            _logger.info(
                "prompt_registry_loaded key=%s hash=%s tier=%s source=%s",
                definition.id,
                definition.hash,
                definition.tier.value,
                definition.source_file,
            )
            new_snapshot[definition.id] = {
                "prompt_hash": definition.hash,
                "source_file": definition.source_file,
                "loaded_at": datetime.now(UTC).isoformat(),
            }
        if self._state_file is not None:
            write_snapshot(self._state_file, new_snapshot)

    def _load_one(self, yaml_path: Path) -> PromptDefinition:
        source_file = yaml_path.name
        expected_id = yaml_path.stem
        raw_bytes = yaml_path.read_bytes()
        content_hash = hashlib.sha256(raw_bytes).hexdigest()[:12]

        try:
            parsed = yaml.safe_load(raw_bytes)
        except yaml.YAMLError as exc:
            raise PromptSchemaError(source_file, f"YAML parse error: {exc}") from exc
        if not isinstance(parsed, dict):
            raise PromptSchemaError(source_file, "top-level YAML must be a mapping")

        for field in _REQUIRED_FIELDS:
            if field not in parsed:
                raise PromptSchemaError(source_file, f"missing required field {field!r}")

        prompt_id = parsed["id"]
        if not isinstance(prompt_id, str) or prompt_id != expected_id:
            raise PromptSchemaError(
                source_file,
                f"id {prompt_id!r} must match filename stem {expected_id!r}",
            )

        tier_raw = parsed["tier"]
        try:
            tier = Tier(tier_raw)
        except ValueError as exc:
            valid = [t.value for t in Tier]
            raise PromptSchemaError(
                source_file, f"tier {tier_raw!r} not in {valid}"
            ) from exc

        placeholders = parsed["placeholders"]
        if not isinstance(placeholders, list) or not all(
            isinstance(p, str) for p in placeholders
        ):
            raise PromptSchemaError(source_file, "placeholders must be a list of strings")

        template = parsed["user_template"]
        if not isinstance(template, str):
            raise PromptSchemaError(source_file, "user_template must be a string")

        declared = set(placeholders)
        found_in_template = set(_PLACEHOLDER_RE.findall(template))
        if declared != found_in_template:
            declared_not_used = declared - found_in_template
            used_not_declared = found_in_template - declared
            raise PromptSchemaError(
                source_file,
                (
                    "placeholders declaration does not match user_template — "
                    f"declared-not-used={sorted(declared_not_used)} "
                    f"used-not-declared={sorted(used_not_declared)}"
                ),
            )

        output_schema = parsed["output_schema"]
        if not isinstance(output_schema, dict):
            raise PromptSchemaError(source_file, "output_schema must be a mapping")

        max_tokens = parsed["max_tokens"]
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens <= 0:
            raise PromptSchemaError(source_file, "max_tokens must be a positive integer")

        temperature = parsed["temperature"]
        if (
            isinstance(temperature, bool)
            or not isinstance(temperature, (int, float))
            or not 0.0 <= float(temperature) <= 2.0
        ):
            raise PromptSchemaError(source_file, "temperature must be in [0.0, 2.0]")

        notes = parsed["notes"]
        return PromptDefinition(
            id=prompt_id,
            description=str(parsed["description"]),
            owner=str(parsed["owner"]),
            tier=tier,
            max_tokens=max_tokens,
            temperature=float(temperature),
            system=str(parsed["system"]),
            user_template=template,
            placeholders=tuple(placeholders),
            output_schema=dict(output_schema),
            created_at=str(parsed["created_at"]),
            notes=str(notes) if notes is not None else None,
            hash=content_hash,
            source_file=source_file,
        )
