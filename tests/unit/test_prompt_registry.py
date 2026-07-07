"""Unit tests for the L0 prompt registry.

Offline. Uses ``tmp_path`` fixtures to isolate the file system.

Covers ADR-0009:
    - §3 schema validation (required fields, id-matches-filename, placeholder
      set matches user_template, tier enum, numeric field ranges)
    - §4 content hash (deterministic, sha256[:12], changes with content)
    - §5 load semantics (drift log on hash change, no drift on match,
      snapshot written, corrupt snapshot treated as first run)
    - §6 render contract (missing / extra / auto-conflict placeholders,
      output_schema inlined via {output_schema_inline})

Also verifies exception hierarchy — ``PromptSchemaError`` and
``PromptNotFoundError`` are both ``PromptRegistryError``; ``PromptRenderError``
is intentionally not (rendering failures are caller bugs, not registry bugs).

Windows note: helper writes bytes (not text) so ``sha256`` is stable across
OSes — ``Path.write_text`` translates ``\\n`` to ``\\r\\n`` on Windows and
would break hash reproducibility.
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from textwrap import dedent

import pytest

from L0_observability.prompt_registry import (
    FileBackedPromptRegistry,
    PromptDefinition,
    PromptNotFoundError,
    PromptRegistryError,
    PromptRenderError,
    PromptRenderer,
    PromptSchemaError,
)
from L6_adapters.ai_gateway import Tier

# --------------------------------------------------------------------- fixtures

_MINIMAL_VALID_YAML = dedent(
    """\
    id: sample_prompt
    description: Sample prompt for tests.
    owner: prav
    tier: balanced
    max_tokens: 1200
    temperature: 0.2
    system: You are a test system prompt.
    user_template: |-
      Data: {data_bundle}
      Return JSON: {output_schema_inline}
    placeholders:
      - data_bundle
      - output_schema_inline
    output_schema:
      result: "string, short answer"
    created_at: '2026-07-07'
    notes: Test entry.
    """
)


def _write_yaml(dir_path: Path, filename: str, content: str) -> Path:
    """Write bytes (not text) — see module docstring on Windows CRLF."""
    path = dir_path / filename
    path.write_bytes(content.encode("utf-8"))
    return path


def _prompts_dir(tmp_path: Path, content: str = _MINIMAL_VALID_YAML) -> Path:
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    _write_yaml(prompts, "sample_prompt.yaml", content)
    return prompts


# --------------------------------------------------------------------- load happy


def test_load_happy_path_returns_definition_with_correct_fields(tmp_path: Path):
    reg = FileBackedPromptRegistry(prompts_dir=_prompts_dir(tmp_path), state_file=None)
    d = reg.get("sample_prompt")
    assert isinstance(d, PromptDefinition)
    assert d.id == "sample_prompt"
    assert d.description == "Sample prompt for tests."
    assert d.owner == "prav"
    assert d.tier == Tier.BALANCED
    assert d.max_tokens == 1200
    assert d.temperature == pytest.approx(0.2)
    assert d.system == "You are a test system prompt."
    assert d.placeholders == ("data_bundle", "output_schema_inline")
    assert d.output_schema == {"result": "string, short answer"}
    assert d.created_at == "2026-07-07"
    assert d.notes == "Test entry."
    assert d.source_file == "sample_prompt.yaml"


def test_load_computes_sha256_first_12_hex_deterministically(tmp_path: Path):
    reg = FileBackedPromptRegistry(prompts_dir=_prompts_dir(tmp_path), state_file=None)
    d = reg.get("sample_prompt")
    expected = hashlib.sha256(_MINIMAL_VALID_YAML.encode("utf-8")).hexdigest()[:12]
    assert d.hash == expected
    assert len(d.hash) == 12
    assert all(c in "0123456789abcdef" for c in d.hash)


def test_hash_changes_when_content_changes(tmp_path: Path):
    prompts = _prompts_dir(tmp_path)
    reg1 = FileBackedPromptRegistry(prompts_dir=prompts, state_file=None)
    h1 = reg1.get("sample_prompt").hash
    # Overwrite with an added comment line — semantically identical, hash-different.
    _write_yaml(prompts, "sample_prompt.yaml", _MINIMAL_VALID_YAML + "# tweak\n")
    reg2 = FileBackedPromptRegistry(prompts_dir=prompts, state_file=None)
    h2 = reg2.get("sample_prompt").hash
    assert h1 != h2


def test_keys_and_all_return_sorted_view(tmp_path: Path):
    prompts = _prompts_dir(tmp_path)
    other = _MINIMAL_VALID_YAML.replace("id: sample_prompt", "id: alpha_prompt")
    _write_yaml(prompts, "alpha_prompt.yaml", other)
    reg = FileBackedPromptRegistry(prompts_dir=prompts, state_file=None)
    assert reg.keys() == ["alpha_prompt", "sample_prompt"]
    assert set(reg.all()) == {"alpha_prompt", "sample_prompt"}


# --------------------------------------------------------------------- schema errors


def test_missing_required_field_raises(tmp_path: Path):
    bad = "\n".join(
        line for line in _MINIMAL_VALID_YAML.splitlines() if not line.startswith("system:")
    )
    with pytest.raises(PromptSchemaError, match="missing required field 'system'"):
        FileBackedPromptRegistry(prompts_dir=_prompts_dir(tmp_path, bad), state_file=None)


def test_wrong_tier_raises(tmp_path: Path):
    bad = _MINIMAL_VALID_YAML.replace("tier: balanced", "tier: purple")
    with pytest.raises(PromptSchemaError, match="tier 'purple' not in"):
        FileBackedPromptRegistry(prompts_dir=_prompts_dir(tmp_path, bad), state_file=None)


def test_id_mismatch_filename_raises(tmp_path: Path):
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    # filename says different_name; id inside says sample_prompt.
    _write_yaml(prompts, "different_name.yaml", _MINIMAL_VALID_YAML)
    with pytest.raises(PromptSchemaError, match="must match filename stem"):
        FileBackedPromptRegistry(prompts_dir=prompts, state_file=None)


def test_placeholder_declared_but_not_in_template_raises(tmp_path: Path):
    bad = _MINIMAL_VALID_YAML.replace(
        "- output_schema_inline", "- output_schema_inline\n  - unused_slot"
    )
    with pytest.raises(PromptSchemaError, match="declared-not-used=\\['unused_slot'\\]"):
        FileBackedPromptRegistry(prompts_dir=_prompts_dir(tmp_path, bad), state_file=None)


def test_placeholder_used_but_not_declared_raises(tmp_path: Path):
    bad = _MINIMAL_VALID_YAML.replace(
        "Data: {data_bundle}",
        "Data: {data_bundle}\n  Extra: {undeclared_slot}",
    )
    with pytest.raises(
        PromptSchemaError, match="used-not-declared=\\['undeclared_slot'\\]"
    ):
        FileBackedPromptRegistry(prompts_dir=_prompts_dir(tmp_path, bad), state_file=None)


def test_bad_max_tokens_raises(tmp_path: Path):
    bad = _MINIMAL_VALID_YAML.replace("max_tokens: 1200", "max_tokens: -5")
    with pytest.raises(PromptSchemaError, match="max_tokens must be a positive integer"):
        FileBackedPromptRegistry(prompts_dir=_prompts_dir(tmp_path, bad), state_file=None)


def test_boolean_max_tokens_rejected(tmp_path: Path):
    # Guard against ``isinstance(True, int) is True`` — YAML "true" would slip through
    # a bare integer check and register max_tokens=1.
    bad = _MINIMAL_VALID_YAML.replace("max_tokens: 1200", "max_tokens: true")
    with pytest.raises(PromptSchemaError, match="max_tokens must be a positive integer"):
        FileBackedPromptRegistry(prompts_dir=_prompts_dir(tmp_path, bad), state_file=None)


def test_bad_temperature_raises(tmp_path: Path):
    bad = _MINIMAL_VALID_YAML.replace("temperature: 0.2", "temperature: 3.0")
    with pytest.raises(PromptSchemaError, match="temperature must be in"):
        FileBackedPromptRegistry(prompts_dir=_prompts_dir(tmp_path, bad), state_file=None)


def test_prompts_dir_missing_raises(tmp_path: Path):
    with pytest.raises(PromptRegistryError, match="prompts directory does not exist"):
        FileBackedPromptRegistry(prompts_dir=tmp_path / "does_not_exist", state_file=None)


def test_yaml_parse_error_wrapped_as_schema_error(tmp_path: Path):
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    _write_yaml(prompts, "sample_prompt.yaml", "not: valid: yaml: [")
    with pytest.raises(PromptSchemaError, match="YAML parse error"):
        FileBackedPromptRegistry(prompts_dir=prompts, state_file=None)


# --------------------------------------------------------------------- lookup


def test_get_unknown_key_raises_with_known_list(tmp_path: Path):
    reg = FileBackedPromptRegistry(prompts_dir=_prompts_dir(tmp_path), state_file=None)
    with pytest.raises(PromptNotFoundError) as info:
        reg.get("does_not_exist")
    assert "sample_prompt" in str(info.value)
    assert info.value.key == "does_not_exist"


def test_exception_hierarchy():
    # Consumers can catch PromptRegistryError to catch all registry-side failures.
    assert issubclass(PromptSchemaError, PromptRegistryError)
    assert issubclass(PromptNotFoundError, PromptRegistryError)
    # Render errors are distinct — caller bug, not registry state.
    assert not issubclass(PromptRenderError, PromptRegistryError)


# --------------------------------------------------------------------- snapshot / drift


def test_snapshot_written_on_first_load(tmp_path: Path):
    prompts = _prompts_dir(tmp_path)
    state = tmp_path / "state" / "prompt_registry_state.json"
    FileBackedPromptRegistry(prompts_dir=prompts, state_file=state)
    assert state.exists(), "snapshot file should be created on first load"
    data = json.loads(state.read_text(encoding="utf-8"))
    assert "written_at" in data
    assert "prompts" in data
    entry = data["prompts"]["sample_prompt"]
    assert entry["source_file"] == "sample_prompt.yaml"
    assert (
        entry["prompt_hash"]
        == hashlib.sha256(_MINIMAL_VALID_YAML.encode("utf-8")).hexdigest()[:12]
    )
    assert "loaded_at" in entry


def test_drift_warn_on_hash_change(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    prompts = _prompts_dir(tmp_path)
    state = tmp_path / "prompt_registry_state.json"
    # Pre-seed a snapshot with a fake old hash so we force a drift line.
    state.write_text(
        json.dumps(
            {
                "prompts": {
                    "sample_prompt": {
                        "prompt_hash": "deadbeefcafe",
                        "source_file": "sample_prompt.yaml",
                        "loaded_at": "2026-07-06T00:00:00+00:00",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    with caplog.at_level(logging.WARNING, logger="signalcare.prompt_registry"):
        FileBackedPromptRegistry(prompts_dir=prompts, state_file=state)
    assert any(
        "prompt_drift" in rec.message
        and "sample_prompt" in rec.message
        and "deadbeefcafe" in rec.message
        for rec in caplog.records
    ), f"expected a prompt_drift WARN line, got {[r.message for r in caplog.records]}"


def test_no_drift_warn_when_hash_matches(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    prompts = _prompts_dir(tmp_path)
    current_hash = hashlib.sha256(_MINIMAL_VALID_YAML.encode("utf-8")).hexdigest()[:12]
    state = tmp_path / "prompt_registry_state.json"
    state.write_text(
        json.dumps(
            {
                "prompts": {
                    "sample_prompt": {
                        "prompt_hash": current_hash,
                        "source_file": "sample_prompt.yaml",
                        "loaded_at": "2026-07-06T00:00:00+00:00",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    with caplog.at_level(logging.WARNING, logger="signalcare.prompt_registry"):
        FileBackedPromptRegistry(prompts_dir=prompts, state_file=state)
    assert not any(
        "prompt_drift" in rec.message for rec in caplog.records
    ), "hash matched prior snapshot — no drift line should have fired"


def test_corrupt_snapshot_treated_as_first_run(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    prompts = _prompts_dir(tmp_path)
    state = tmp_path / "prompt_registry_state.json"
    state.write_text("not valid json {", encoding="utf-8")
    with caplog.at_level(
        logging.WARNING, logger="signalcare.prompt_registry.snapshot"
    ):
        FileBackedPromptRegistry(prompts_dir=prompts, state_file=state)
    assert any(
        "prompt_registry_snapshot_corrupt" in rec.message for rec in caplog.records
    )
    # A fresh snapshot is written over the corrupt file.
    data = json.loads(state.read_text(encoding="utf-8"))
    assert "sample_prompt" in data["prompts"]


def test_no_state_file_disables_snapshot(tmp_path: Path):
    # state_file=None is a valid mode (used in tests + read-only startups).
    prompts = _prompts_dir(tmp_path)
    reg = FileBackedPromptRegistry(prompts_dir=prompts, state_file=None)
    assert reg.get("sample_prompt") is not None
    # No stray snapshot file should have been created anywhere in tmp_path.
    assert not any(p.name.endswith(".json") for p in tmp_path.rglob("*"))


# --------------------------------------------------------------------- renderer


def _load_sample_definition(tmp_path: Path) -> PromptDefinition:
    return FileBackedPromptRegistry(
        prompts_dir=_prompts_dir(tmp_path), state_file=None
    ).get("sample_prompt")


def test_render_happy_path_substitutes_placeholders(tmp_path: Path):
    definition = _load_sample_definition(tmp_path)
    system, user = PromptRenderer().render(definition, data_bundle="the data payload")
    assert system == "You are a test system prompt."
    assert "Data: the data payload" in user
    assert "Return JSON:" in user


def test_render_inlines_output_schema_as_json(tmp_path: Path):
    definition = _load_sample_definition(tmp_path)
    _, user = PromptRenderer().render(definition, data_bundle="x")
    # The template's {output_schema_inline} slot is auto-filled with JSON of the schema.
    assert "{output_schema_inline}" not in user
    # And the schema content is embedded, JSON-encoded.
    assert '"result"' in user
    assert "string, short answer" in user


def test_render_missing_placeholder_raises(tmp_path: Path):
    definition = _load_sample_definition(tmp_path)
    with pytest.raises(PromptRenderError, match="missing=\\['data_bundle'\\]"):
        PromptRenderer().render(definition)


def test_render_extra_placeholder_raises(tmp_path: Path):
    definition = _load_sample_definition(tmp_path)
    with pytest.raises(PromptRenderError, match="extra=\\['surprise'\\]"):
        PromptRenderer().render(definition, data_bundle="x", surprise="y")


def test_render_caller_supplying_output_schema_inline_raises(tmp_path: Path):
    definition = _load_sample_definition(tmp_path)
    with pytest.raises(PromptRenderError, match="must not supply"):
        PromptRenderer().render(
            definition, data_bundle="x", output_schema_inline="attempt to override"
        )


# --------------------------------------------------------------------- integration
# One end-to-end that exercises the actual compliance_ops_digest.yaml file to
# make sure the shipped prompt loads under the same validator that the tests
# above exercise with synthetic YAML.


def test_shipped_compliance_ops_digest_yaml_loads(tmp_path: Path):
    real_prompts = (
        Path(__file__).resolve().parents[2] / "app" / "L0_observability" / "prompts"
    )
    reg = FileBackedPromptRegistry(prompts_dir=real_prompts, state_file=None)
    d = reg.get("compliance_ops_digest")
    assert d.tier == Tier.BALANCED
    assert d.max_tokens == 1200
    assert "output_schema_inline" in d.placeholders
    # ADR-0008 §5 lists these input placeholders; keep them in sync.
    for required in (
        "host_stats",
        "adapter_health",
        "hardening_status",
        "guardrail_activity_24h",
    ):
        assert required in d.placeholders, (
            f"placeholder {required!r} missing from shipped digest prompt "
            f"— ADR-0008 §5 requires it"
        )


def test_shipped_digest_renders_with_placeholder_values(tmp_path: Path):
    real_prompts = (
        Path(__file__).resolve().parents[2] / "app" / "L0_observability" / "prompts"
    )
    reg = FileBackedPromptRegistry(prompts_dir=real_prompts, state_file=None)
    d = reg.get("compliance_ops_digest")
    system, user = PromptRenderer().render(
        d,
        host_stats="cpu 42%, mem 61%, disk 79%",
        adapter_health="ollama green, anthropic green",
        hardening_status="all 8 controls compliant",
        guardrail_activity_24h="phi_redactions=41 (T1=4 T2=29 T3=8) baa=0 injection_blocks=2 injection_flags=1",
    )
    assert "senior operations analyst" in system
    assert "cpu 42%" in user
    assert "{output_schema_inline}" not in user
    assert '"attention"' in user
