"""L3 compliance_ops · JSON → markdown renderer.

Deterministic converter. Takes the normalized digest dict produced by
``ComplianceOpsAgent`` (LLM output post-processed: guardrail counts
overwritten from source-of-truth, arrays capped at 3, every required
key present) and produces the fixed-5-section markdown per ADR-0008
Appendix A / B mockups.

Deliberately stupid. No severity colouring, no trend arrows, no branchy
logic beyond section-emptiness. Any complex formatting decision belongs
in the agent or its inputs, not here — the ADR says so and the mockups
enforce it.

Structural invariants (locked by ADR-0008):
- Fixed 5 sections in fixed order: Attention / Watch / Guardrails /
  Systems / Decisions I need.
- Empty arrays render as ``None.`` (literal, with the period).
- Attention / Watch / Decisions items: bolded head + indented body.
- Guardrails: single ``·``-separated line with computed counts.
- Systems: ``- name: state`` with optional ``— note`` suffix.
"""
from __future__ import annotations


def render_markdown(digest: dict) -> str:
    """Produce the ADR-0008 markdown for a normalized digest dict.

    Consumer contract: ``digest`` includes ``date``, ``attention``,
    ``watch``, ``guardrails``, ``systems``, ``decisions``. Missing keys
    render as empty sections; that is a defensive fallback, not a
    supported call — well-formed input comes from the agent, always.
    """
    lines: list[str] = [f"# SignalCare Ops Digest — {digest.get('date', 'unknown-date')}", ""]

    lines.append("## Attention")
    lines.append("")
    _render_headline_body_section(lines, digest.get("attention"), "headline", "evidence")
    lines.append("")

    lines.append("## Watch")
    lines.append("")
    _render_headline_body_section(lines, digest.get("watch"), "headline", "evidence")
    lines.append("")

    lines.append("## Guardrails")
    lines.append("")
    lines.append(_render_guardrails_line(digest.get("guardrails", {})))
    lines.append("")

    lines.append("## Systems")
    lines.append("")
    _render_systems(lines, digest.get("systems"))
    lines.append("")

    lines.append("## Decisions I need")
    lines.append("")
    _render_headline_body_section(lines, digest.get("decisions"), "question", "context")

    return "\n".join(lines) + "\n"


def _render_headline_body_section(
    lines: list[str],
    items: list[dict] | None,
    head_key: str,
    body_key: str,
) -> None:
    if not items:
        lines.append("None.")
        return
    for item in items:
        head = str(item.get(head_key, "")).strip()
        body = str(item.get(body_key, "")).strip()
        lines.append(f"- **{head}**")
        if body:
            lines.append(f"  {body}")


def _render_guardrails_line(guardrails: dict) -> str:
    """Emit the single-line summary. Counts come from source-of-truth —
    the agent overwrites LLM output before this renderer runs, so we trust
    the values here.
    """
    phi = guardrails.get("phi_redactions") or {}
    total = phi.get("total", 0)
    t1 = phi.get("T1", 0)
    t2 = phi.get("T2", 0)
    t3 = phi.get("T3", 0)
    return (
        f"24h counts: PHI redactions {total} (T1 {t1} / T2 {t2} / T3 {t3}) · "
        f"BAA blocks {guardrails.get('baa_blocks', 0)} · "
        f"Injection blocks {guardrails.get('injection_blocks', 0)} · "
        f"Injection flags {guardrails.get('injection_flags', 0)}"
    )


def _render_systems(lines: list[str], systems: list[dict] | None) -> None:
    if not systems:
        lines.append("None.")
        return
    for entry in systems:
        name = str(entry.get("name", "unknown"))
        state = str(entry.get("state", "unknown"))
        note = entry.get("note")
        if note:
            lines.append(f"- {name}: {state} — {str(note).strip()}")
        else:
            lines.append(f"- {name}: {state}")
