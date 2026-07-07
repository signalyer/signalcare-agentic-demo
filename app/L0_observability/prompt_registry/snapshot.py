"""Prompt-registry state snapshot — the drift-detection sidecar.

The snapshot is a small JSON sidecar written by the registry after every
successful startup load. On the *next* startup, the registry compares each
prompt's freshly-computed content hash against the value it snapshotted
last time and logs a WARN line for every changed hash.

Design notes
------------
- Missing snapshot → treated as first-run. No WARNs; a fresh snapshot is
  written after the load completes. Same treatment for a corrupt or
  malformed file — the alternative (refuse to boot on a bad sidecar file)
  would make the audit trail a boot-blocker, which is the wrong tradeoff.
- The wrapper object (``{"written_at": ..., "prompts": {...}}``) exists so
  future readers can add metadata additively without a migration pass.
- The file is a runtime artifact; ``.gitignore`` keeps it out of git. Git
  already tracks the YAML source of truth; the snapshot's only reader is
  the next startup's drift comparator.

See ADR-0009 §5.5–5.7.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

_logger = logging.getLogger("signalcare.prompt_registry.snapshot")


def read_snapshot(path: Path) -> dict[str, dict]:
    """Read the previous snapshot's ``prompts`` map, or return ``{}`` on any failure.

    Return shape: ``{prompt_id: {"prompt_hash", "source_file", "loaded_at"}}``.
    Corrupt or malformed files log WARN and return an empty map — first-run
    treatment. See module docstring for why boot-blocking would be wrong.
    """
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        _logger.warning(
            "prompt_registry_snapshot_corrupt path=%s err=%s -- treating as first run",
            path,
            exc,
        )
        return {}
    prompts = data.get("prompts") if isinstance(data, dict) else None
    if not isinstance(prompts, dict):
        _logger.warning(
            "prompt_registry_snapshot_malformed path=%s -- treating as first run",
            path,
        )
        return {}
    return prompts


def write_snapshot(path: Path, entries: dict[str, dict]) -> None:
    """Overwrite the snapshot file with the current entries.

    Creates the parent directory if missing. Sorted keys so diffs across
    runs are stable and reviewable by eye.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "written_at": datetime.now(UTC).isoformat(),
        "prompts": entries,
    }
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
