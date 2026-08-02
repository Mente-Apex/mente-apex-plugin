"""Rendering a GateResult into the lens's report.

Never a percentage: "87%" tells an operator nothing actionable, and a threshold
gets gamed. What they need is "this mutant survived and these tests should have
killed it".

Inconclusive results get their own section rather than being folded into either
column, because a timed-out mutant reported as silence reads exactly like a
clean run.

`survived_minor` (the prose backend's lower-tier `invert`-operator finding) is
a real survivor, not an inconclusive result -- it renders under the same
Survivors headline as a plain `survived`, with its own status named inline so
the tier the backend deliberately encoded stays visible rather than being
either lost (promoted silently to `survived`) or hidden (misfiled as
inconclusive).

`unresolved` and `unclaimed` get their own sections too, and deliberately
different wording: `unresolved` is a suffix no stack owns at all (may be
perfectly fine — an image, a lockfile), `unclaimed` is a file that landed in a
known stack partition for which no backend was registered this run (a
misconfiguration the operator can fix by registering a backend). Folding them
into one label would hide the second behind the first.

`run_errors` gets its own section too, rendered like `baseline_error`: one
named fact per backend whose tool run did not complete (mutmut's stats
collection crashing before a single mutant executed is the reproduced case),
not one row per mutant that failure left unchecked. Folding a crashed run's
fallout into `Inconclusive` line-by-line would turn one system failure into a
flood of near-duplicate rows -- worse for an operator than the silence it
replaces, and not the "signal" this report exists to provide.
"""

from mutation_gate import is_survivor, unverified_reasons

# The contract between this renderer and `references/report-template.md`. The
# gate does not append its section, and does not own the file: it replaces
# exactly the span between these two markers and leaves every other byte of the
# operator's report alone, so a re-run updates the section in place instead of
# accumulating a stack of stale ones. Changing either string is a breaking
# change to every report already carrying the pair.
BEGIN_MARKER = "<!-- mutation-gate:begin -->"
END_MARKER = "<!-- mutation-gate:end -->"

# A `run_errors` message can carry a raw tool dump (a crash traceback, or one
# `not checked` line per mutant collection never got to) many KB long. The
# JSON payload keeps that in full -- it is the analyzer's channel. This
# renderer is the operator's channel, so it bounds the dump to a head/tail
# excerpt: enough real lines to see WHAT failed, never the whole thing, and
# never silence about how much was cut.
_RUN_ERROR_HEAD_LINES = 15
_RUN_ERROR_TAIL_LINES = 15
_RUN_ERROR_LINE_MAX_CHARS = 300

# A survivor's diff is bounded for the same reason a `run_errors` dump is, and
# it was not: one survivor's diff is small, but a backend reporting hundreds of
# them splices an arbitrarily large blob into the operator's report file. The
# JSON payload still carries every diff in full.
_DIFF_MAX_LINES = 20


def _clip_line(line):
    """Bound one line's length so a single absurd line can't dominate."""
    if len(line) <= _RUN_ERROR_LINE_MAX_CHARS:
        return line
    omitted = len(line) - _RUN_ERROR_LINE_MAX_CHARS
    return f"{line[:_RUN_ERROR_LINE_MAX_CHARS]}... [{omitted} more chars]"


def _render_run_error(message):
    """Render one `run_errors` entry as real, bounded lines.

    A short, single-line message (no attached tool dump) renders exactly as
    before: `- {message}`. A message with an attached multi-line dump keeps
    its first line (the human summary) as the bullet, then bounds the dump
    to a head/tail excerpt inside a collapsed, fenced code block -- stating
    the full size and line count so nothing is hidden by accident.
    """
    lines = message.splitlines()
    if len(lines) <= 1:
        return [f"- {message}"]

    summary, *dump_lines = lines
    dump_lines = [_clip_line(line) for line in dump_lines]
    total_chars = len(message)
    total_dump_lines = len(dump_lines)

    budget = _RUN_ERROR_HEAD_LINES + _RUN_ERROR_TAIL_LINES
    if total_dump_lines <= budget:
        excerpt = dump_lines
    else:
        omitted = total_dump_lines - budget
        excerpt = (
            dump_lines[:_RUN_ERROR_HEAD_LINES]
            + [f"... [{omitted} more lines elided] ..."]
            + dump_lines[-_RUN_ERROR_TAIL_LINES:]
        )

    out = [
        f"- {summary}",
        f"  ({total_chars} bytes, {total_dump_lines} raw output line"
        f"{'' if total_dump_lines == 1 else 's'} — truncated below; full "
        "detail is in the JSON payload)",
        "",
        "  <details><summary>tool output (truncated)</summary>",
        "",
        "  ```",
    ]
    out.extend(f"  {line}" for line in excerpt)
    out.extend(["  ```", "", "  </details>", ""])
    return out


def splice_into_report(report_text, section):
    """Return `report_text` with `section` between the mutation-gate markers.

    Every malformed case raises rather than degrading to "leave it alone" or
    "append at the end": a report that silently keeps reading `_Not yet run._`
    after a real run is exactly the silence-as-a-pass this lens exists to
    stop, and it would be indistinguishable from a gate that found nothing.
    """
    begin = report_text.find(BEGIN_MARKER)
    end = report_text.find(END_MARKER)
    if begin == -1 or end == -1:
        raise ValueError(
            f"report has no mutation-gate markers ({BEGIN_MARKER} / "
            f"{END_MARKER}); the gate will not guess where its section "
            "belongs -- add the pair (see references/report-template.md)"
        )
    if end < begin:
        raise ValueError(
            f"mutation-gate markers are in the wrong order: {END_MARKER} "
            f"precedes {BEGIN_MARKER}"
        )
    if (
        report_text.find(BEGIN_MARKER, begin + 1) != -1
        or report_text.find(END_MARKER, end + 1) != -1
    ):
        raise ValueError(
            "a mutation-gate marker appears more than once; the gate will "
            "not guess which pair delimits the section"
        )
    return (
        report_text[: begin + len(BEGIN_MARKER)]
        + "\n"
        + section.strip("\n")
        + "\n"
        + report_text[end:]
    )


def _mutants_executed_summary(result):
    """How many mutants actually ran, per backend, on the headline line.

    Printed next to "Files selected" because the two together are what tell an
    operator whether an empty survivor list means anything: 12 files selected
    and 0 mutants executed is a vacuous run, and read identically to a real
    one until this number was on the page. A backend that does not report a
    count says so rather than contributing a silent 0.
    """
    if not result.backend_runs:
        return "0 (no backend ran)"
    parts = []
    for backend_run in result.backend_runs:
        count = backend_run.mutants_executed
        parts.append(
            f"{backend_run.tool}: " + ("not reported" if count is None else str(count))
        )
    return ", ".join(parts)


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
                "status": s.status,
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
        "run_errors": list(result.run_errors),
        "scope_notes": list(result.scope_notes),
        "selected": result.selected,
        "backend_runs": [
            {
                "stack": backend_run.stack,
                "tool": backend_run.tool,
                "mutants_executed": backend_run.mutants_executed,
            }
            for backend_run in result.backend_runs
        ],
        # The analyzer agent reads this payload, not the markdown, so the
        # verdict has to be here too -- otherwise the one consumer that acts
        # on the result programmatically is the one that cannot tell a clean
        # run from a run that never looked.
        "unverified_reasons": list(unverified_reasons(result)),
    }


def render_markdown(result, scope):
    """The Mutation-gate section body for the report."""
    unverified = unverified_reasons(result)
    lines = [
        f"**Scope:** {scope}",
        f"**Files selected:** {result.selected}",
        f"**Mutants executed:** {_mutants_executed_summary(result)}",
        "",
    ]

    if result.baseline_error:
        lines.append(
            "**Baseline did not complete** — the clean-run baseline never "
            "finished, so the survived/unreliable split below is unverified, "
            f"not clean: {result.baseline_error}"
        )
        lines.append("")

    if result.run_errors:
        lines.append(
            "**Run errors** — a backend's tool run did not complete, so no "
            "per-mutant result from it below can be trusted:"
        )
        lines.append("")
        for message in result.run_errors:
            lines.extend(_render_run_error(message))
        lines.append("")

    if result.scope_notes:
        # Deliberately NOT folded into `run_errors`. These runs COMPLETED and
        # their per-mutant results are trustworthy -- printing the "did not
        # complete" banner over them would be its own kind of lie. What they
        # covered is narrower (or wider) than what was selected, and an empty
        # survivor list under a silently-widened scope reads exactly like a
        # clean one, which is the failure this section exists to prevent.
        lines.append(
            "**Scope caveats** — a backend ran to completion but did not "
            "mutate exactly the selection it was handed, so read its results "
            "against the scope named here rather than the one you asked for:"
        )
        lines.append("")
        for note in result.scope_notes:
            lines.append(f"- {note}")
        lines.append("")

    if unverified:
        # Its own block, printed BEFORE the survivor section and independent of
        # it. Hanging these off the "no survivors" branch meant a run with both
        # a survivor and an unverified scope printed neither the reasons nor
        # any hint that the scope was incomplete -- while still exiting 2, and
        # while the agent docs told the reviewer to go read the reasons.
        lines.append(
            "**This run did not verify its whole scope** — some of the files "
            "below were never mutated, so an absence of findings among them "
            "is an absence of data:"
        )
        lines.append("")
        for reason in unverified:
            lines.append(f"- {reason}")
        lines.append("")

    survived = [s for s in result.survivors if is_survivor(s)]
    if survived:
        lines.append("**Survivors** — a mutant these tests failed to kill:")
        lines.append("")
        for survivor in survived:
            tier = "" if survivor.status == "survived" else f", {survivor.status}"
            lines.append(
                f"- `{survivor.location}` — {survivor.mutant} "
                f"(via {survivor.backend}, {survivor.granularity} granularity{tier})"
            )
            for test in survivor.associated_tests:
                lines.append(f"  - should have killed it: `{test}`")
            if survivor.mutant_diff:
                lines.append("")
                lines.append("    ```diff")
                diff_lines = survivor.mutant_diff.splitlines()
                for diff_line in diff_lines[:_DIFF_MAX_LINES]:
                    lines.append(f"    {_clip_line(diff_line)}")
                if len(diff_lines) > _DIFF_MAX_LINES:
                    omitted = len(diff_lines) - _DIFF_MAX_LINES
                    lines.append(
                        f"    ... [{omitted} more diff lines elided — full "
                        "diff is in the JSON payload]"
                    )
                lines.append("    ```")
        lines.append("")
    elif unverified:
        # Never "No survivors in scope." here. An empty survivor list from a
        # run that could not look is an ABSENCE OF DATA, and printing the
        # clean-run sentence over it is how a failed run reads as a pass. The
        # reasons themselves are already listed above, in their own block, so
        # they reach the operator whether or not there were survivors too.
        lines.append(
            "**No survivors reported, and this run did not verify its "
            "scope** — see the reasons above. An empty survivor list here "
            "means the gate could not look, not that it looked and found "
            "nothing; this is not a clean result."
        )
        lines.append("")
    elif not result.selected:
        # "Nothing to do" is a different fact from "nothing found", and an
        # all-empty result cannot tell them apart on its own.
        lines.append(
            "**Nothing selected** — no files were selected for this scope, so "
            "nothing was mutated. This is 'nothing to do', not 'nothing found'."
        )
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
