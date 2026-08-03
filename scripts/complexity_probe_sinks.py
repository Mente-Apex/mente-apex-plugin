"""Where a report goes: the transcript, the audit artifact, or a review.

One producer, three consumers — the probe does not know which sink it feeds,
which is what lets the same lizard run serve the TDD cycle, the Phase 0
Measurements artifact and on-demand chunk review without any of them learning
about each other.

No sink words a breach as a failure. A threshold breach is a place to look;
the judgment belongs to a lens, not to a number.

Every sink takes one argument, a `ProbeReport`. It was three, growing by
optional positional parameter as each new thing a sink renders was discovered:
`scope_description` arrived that way and two of the three implementations
silently ignored it, so the text and JSON renderings of one run disagreed about
which target it was. An argument three signatures accept and two drop is not a
contract. The verdict was worse — it never reached a sink at all, and the
caller edited the dict `ArtifactSink` returned, so the audit payload was
assembled in two files. A parameter object gives the port one shape: a fourth
thing to render is a field, not a signature change, and a sink that renders
none of it still cannot disagree with one that does.

`ProbeReport` lives here because a port owns the shape of its own input, and it
carries the verdict as plain data read through `.status` and `.message` — the
sinks import no gate, so the module that decides whether a check was performed
still knows nothing about rendering.
"""

from dataclasses import dataclass

from complexity_probe_measurement import RAN


@dataclass(frozen=True)
class ProbeReport:
    """One run, as everything that renders it needs to see it.

    `scope_description` is the scope's own words for what it selected, because
    "nothing to measure" is two different facts: a target with no functions in
    it, and a target that selected nothing. `File.py:3-4` (two blank lines) and
    a file with no functions used to render byte-identically. It stays `None`
    for a caller with no scope to state — an omitted line, never an invented
    one.

    `verdict` is present only when the caller asked for one (`--gate`), and a
    sink that renders it must leave it out of the payload entirely when it is
    absent rather than emit a null.
    """

    measurement: object
    thresholds: object = None
    scope_description: str | None = None
    verdict: object = None


def _sorted_by_complexity(functions):
    return sorted(
        functions, key=lambda metric: metric.cyclomatic_complexity, reverse=True
    )


def _scope_lines(scope_description):
    """The leading line naming what was measured, or nothing to lead with."""
    return [f"scope: {scope_description}"] if scope_description else []


def _is_worth_a_look(metric, thresholds) -> bool:
    limit = thresholds.cyclomatic_complexity if thresholds else None
    return limit is not None and metric.cyclomatic_complexity > limit


class TranscriptSink:
    """For the TDD cycle: compact lines the agent must answer to."""

    def render(self, report) -> str:
        measurement = report.measurement
        lines = _scope_lines(report.scope_description)
        if not measurement.has_numbers:
            # The scope still belongs here. A probe that could not run says
            # nothing about *what* it could not run against, and the artifact
            # sink records it either way — two renderings of one run must not
            # disagree about which target it was.
            return "\n".join(lines + [f"{measurement.status}: {measurement.reason}"])

        if measurement.functions:
            lines.append(f"measured {len(measurement.functions)} changed function(s):")
            for metric in _sorted_by_complexity(measurement.functions):
                marker = (
                    "   <- worth a look"
                    if _is_worth_a_look(metric, report.thresholds)
                    else ""
                )
                lines.append(
                    f"  {metric.name}  CC {metric.cyclomatic_complexity}"
                    f"  {metric.length} lines{marker}"
                )
        else:
            lines.append("measured the change: no functions touched")

        if measurement.status != RAN:
            lines.append(f"  ({measurement.status}: {measurement.reason})")
            if measurement.skipped:
                lines.append(f"  not covered: {', '.join(measurement.skipped)}")

        return "\n".join(lines)


class ArtifactSink:
    """For the Phase 0 Measurements artifact — data, not prose.

    Owns the whole payload, including the verdict. The caller used to render
    this dict and then add a key to it, which put one schema in two files and
    left the sink named for the artifact not actually in charge of it.
    """

    def render(self, report) -> dict:
        measurement = report.measurement
        thresholds = report.thresholds
        payload = {
            "status": measurement.status,
            "reason": measurement.reason,
            "scope": report.scope_description,
            "skipped": list(measurement.skipped),
            "thresholds": {
                "cyclomatic_complexity": (
                    thresholds.cyclomatic_complexity if thresholds else None
                ),
                "source": thresholds.source if thresholds else "none declared",
                "diagnostics": list(thresholds.diagnostics) if thresholds else [],
            },
            "functions": [
                {
                    "name": metric.name,
                    "path": metric.path,
                    "start_line": metric.start_line,
                    "end_line": metric.end_line,
                    "cyclomatic_complexity": metric.cyclomatic_complexity,
                    "length": metric.length,
                    "parameter_count": metric.parameter_count,
                }
                for metric in measurement.functions
            ],
        }
        if report.verdict is not None:
            # Omitted rather than null when nobody asked for a verdict: a
            # consumer reading `verdict` must be able to tell "the gate said
            # nothing" from "the gate was never consulted".
            payload["verdict"] = {
                "status": report.verdict.status,
                "message": report.verdict.message,
            }
        return payload


class ReviewSink:
    """For on-demand chunk review: outlier first, so a lens knows where to look."""

    def render(self, report) -> str:
        measurement = report.measurement
        lines = _scope_lines(report.scope_description)
        if not measurement.has_numbers:
            # The scope still belongs here. A probe that could not run says
            # nothing about *what* it could not run against, and the artifact
            # sink records it either way — two renderings of one run must not
            # disagree about which target it was.
            return "\n".join(lines + [f"{measurement.status}: {measurement.reason}"])

        if measurement.functions:
            lines.append(f"measured {len(measurement.functions)} function(s):")
            for metric in _sorted_by_complexity(measurement.functions):
                marker = (
                    "   <- outlier, worth a look"
                    if _is_worth_a_look(metric, report.thresholds)
                    else ""
                )
                lines.append(
                    f"  {metric.name}  ({metric.path}:{metric.start_line})"
                    f"  CC {metric.cyclomatic_complexity}"
                    f"  parameters {metric.parameter_count}"
                    f"  {metric.length} lines{marker}"
                )
        else:
            lines.append("measured the chunk: no functions found")

        if measurement.status != RAN:
            lines.append(f"  ({measurement.status}: {measurement.reason})")
            if measurement.skipped:
                lines.append(f"  not covered: {', '.join(measurement.skipped)}")

        return "\n".join(lines)
