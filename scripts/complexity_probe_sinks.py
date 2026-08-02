"""Where a measurement goes: the transcript, the audit artifact, or a review.

One producer, three consumers — the probe does not know which sink it feeds,
which is what lets the same lizard run serve the TDD cycle, the Phase 0
Measurements artifact and on-demand chunk review without any of them learning
about each other.

No sink words a breach as a failure. A threshold breach is a place to look;
the judgment belongs to a lens, not to a number.
"""

from complexity_probe_measurement import RAN


def _sorted_by_complexity(functions):
    return sorted(
        functions, key=lambda metric: metric.cyclomatic_complexity, reverse=True
    )


def _is_worth_a_look(metric, thresholds) -> bool:
    limit = thresholds.cyclomatic_complexity if thresholds else None
    return limit is not None and metric.cyclomatic_complexity > limit


class TranscriptSink:
    """For the TDD cycle: compact lines the agent must answer to."""

    def render(self, measurement, thresholds) -> str:
        if not measurement.has_numbers:
            return f"{measurement.status}: {measurement.reason}"

        if measurement.functions:
            lines = [f"measured {len(measurement.functions)} changed function(s):"]
            for metric in _sorted_by_complexity(measurement.functions):
                marker = (
                    "   <- worth a look" if _is_worth_a_look(metric, thresholds) else ""
                )
                lines.append(
                    f"  {metric.name}  CC {metric.cyclomatic_complexity}"
                    f"  {metric.length} lines{marker}"
                )
        else:
            lines = ["measured the change: no functions touched"]

        if measurement.status != RAN:
            lines.append(f"  ({measurement.status}: {measurement.reason})")
            if measurement.skipped:
                lines.append(f"  not covered: {', '.join(measurement.skipped)}")

        return "\n".join(lines)


class ArtifactSink:
    """For the Phase 0 Measurements artifact — data, not prose."""

    def render(self, measurement, thresholds) -> dict:
        return {
            "status": measurement.status,
            "reason": measurement.reason,
            "skipped": list(measurement.skipped),
            "thresholds": {
                "cyclomatic_complexity": (
                    thresholds.cyclomatic_complexity if thresholds else None
                ),
                "source": thresholds.source if thresholds else "none declared",
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


class ReviewSink:
    """For on-demand chunk review: outlier first, so a lens knows where to look."""

    def render(self, measurement, thresholds) -> str:
        if not measurement.has_numbers:
            return f"{measurement.status}: {measurement.reason}"

        if measurement.functions:
            lines = [f"measured {len(measurement.functions)} function(s):"]
            for metric in _sorted_by_complexity(measurement.functions):
                marker = (
                    "   <- outlier, worth a look"
                    if _is_worth_a_look(metric, thresholds)
                    else ""
                )
                lines.append(
                    f"  {metric.name}  ({metric.path}:{metric.start_line})"
                    f"  CC {metric.cyclomatic_complexity}"
                    f"  parameters {metric.parameter_count}"
                    f"  {metric.length} lines{marker}"
                )
        else:
            lines = ["measured the chunk: no functions found"]

        if measurement.status != RAN:
            lines.append(f"  ({measurement.status}: {measurement.reason})")
            if measurement.skipped:
                lines.append(f"  not covered: {', '.join(measurement.skipped)}")

        return "\n".join(lines)
