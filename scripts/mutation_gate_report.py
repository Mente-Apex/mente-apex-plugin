"""Rendering a GateResult into the lens's report.

Never a percentage: "87%" tells an operator nothing actionable, and a threshold
gets gamed. What they need is "this mutant survived and these tests should have
killed it".

Inconclusive results get their own section rather than being folded into either
column, because a timed-out mutant reported as silence reads exactly like a
clean run.

`unresolved` and `unclaimed` get their own sections too, and deliberately
different wording: `unresolved` is a suffix no stack owns at all (may be
perfectly fine — an image, a lockfile), `unclaimed` is a file that landed in a
known stack partition for which no backend was registered this run (a
misconfiguration the operator can fix by registering a backend). Folding them
into one label would hide the second behind the first.
"""

from mutation_gate import is_survivor


def as_report_payload(result, scope):
    """A JSON-serialisable view for the calling agent."""
    return {
        "scope": scope,
        "survivors": [
            {
                "artifact": s.artifact,
                "location": s.location,
                "mutant": s.mutant,
                "diff": s.mutant_diff,
                "associated_tests": list(s.associated_tests),
                "backend": s.backend,
                "granularity": s.granularity,
            }
            for s in result.survivors
            if is_survivor(s)
        ],
        "inconclusive": [
            {"location": s.location, "mutant": s.mutant, "reason": s.status}
            for s in result.survivors
            if not is_survivor(s)
        ],
        "unavailable": [
            {"stack": stack, "install": hint} for stack, hint in result.unavailable
        ],
        "unresolved": list(result.unresolved),
        "unclaimed": list(result.unclaimed),
        "baseline_failures": list(result.baseline_failures),
        "baseline_error": result.baseline_error,
    }


def render_markdown(result, scope):
    """The Mutation-gate section body for the report."""
    lines = [f"**Scope:** {scope}", ""]

    if result.baseline_error:
        lines.append(
            "**Baseline did not complete** — the clean-run baseline never "
            "finished, so the survived/unreliable split below is unverified, "
            f"not clean: {result.baseline_error}"
        )
        lines.append("")

    survived = [s for s in result.survivors if is_survivor(s)]
    if survived:
        lines.append("**Survivors** — a mutant these tests failed to kill:")
        lines.append("")
        for survivor in survived:
            lines.append(
                f"- `{survivor.location}` — {survivor.mutant} "
                f"(via {survivor.backend}, {survivor.granularity} granularity)"
            )
            for test in survivor.associated_tests:
                lines.append(f"  - should have killed it: `{test}`")
            if survivor.mutant_diff:
                lines.append("")
                lines.append("    ```diff")
                for diff_line in survivor.mutant_diff.splitlines():
                    lines.append(f"    {diff_line}")
                lines.append("    ```")
        lines.append("")
    else:
        lines.append("No survivors in scope.")
        lines.append("")

    inconclusive = [s for s in result.survivors if not is_survivor(s)]
    if inconclusive:
        lines.append("**Inconclusive** — neither killed nor survived:")
        lines.append("")
        for survivor in inconclusive:
            lines.append(
                f"- `{survivor.location}` — {survivor.mutant} ({survivor.status})"
            )
        lines.append("")

    if result.unavailable:
        lines.append("**Backends not available:**")
        lines.append("")
        for stack, hint in result.unavailable:
            lines.append(f"- {stack}: tool not available — declare it with `{hint}`")
        lines.append("")

    if result.unclaimed:
        lines.append(
            "**Unclaimed** — in scope for a known stack, but no backend was "
            "registered to run it this time. Register a backend for this "
            "stack; these files were never mutated:"
        )
        lines.append("")
        for path in result.unclaimed:
            lines.append(f"- `{path}`")
        lines.append("")

    if result.unresolved:
        lines.append(
            "**Unresolved** — file type this lens does not recognise as any "
            "stack (may be fine — e.g. an asset or a lockfile):"
        )
        lines.append("")
        for path in result.unresolved:
            lines.append(f"- `{path}`")
        lines.append("")

    if result.baseline_failures:
        lines.append("**Unreliable baseline** — these tests were already failing:")
        lines.append("")
        for node_id in result.baseline_failures:
            lines.append(f"- `{node_id}`")
        lines.append("")

    return "\n".join(lines)
