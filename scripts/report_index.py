"""Check a consolidated report against its own Findings index.

Three complaints, one root cause. The index is a **dashboard** — apply order,
each finding's status, where the run stands — and until now it was prose that
nothing verified. So:

- **the apply order was not always followed**, because the order was a column
  rather than a queue anything consumed;
- **findings were not stamped**, because a `Status:` line and its index row are
  two places to write the same fact and nothing compared them;
- **the report was hard to read**, partly because a reader who has been misled
  once by a stale status stops trusting the table and starts reading the prose,
  which is the wall of text the index exists to replace.

A prose instruction to "keep the index in sync" is a guard nothing can check.
This is the check.

**Rules are data.** Each rule is a function `(report) -> list[Violation]`
registered in `DEFAULT_RULES`; adding a rule is adding a function, never an edit
to the runner. Each takes the parsed report and knows nothing about Markdown, so
a change to the template's wording touches the parser and nothing else.

**Advisory by default, blocking on request.** `--strict` turns violations into a
non-zero exit for a hook or CI; the plain run reports and exits 0, because a
report that is mid-apply is legitimately inconsistent for as long as one edit
takes.
"""

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# The canonical vocabulary, defined in docs/refactor-workflow.md and transcribed
# here as patterns. Kept as regexes rather than a set because two values carry a
# payload: the winner of a conflict fork, and the primary that subsumed a rider.
STATUS_PATTERNS = (
    r"^pending$",
    r"^applied$",
    r"^applied \(via [^)]+\)$",
    r"^failed \(reverted\)$",
    r"^skipped \(not approved\)$",
    r"^skipped \(lost conflict to [^)]+\)$",
    r"^deferred(?: \(.+\))?$",
)

RESOLVED_STATUSES = ("applied", "failed", "skipped", "deferred")

FINDING_ID = re.compile(r"[a-z-]+/(?:critical|major|minor)-\d+", re.I)
INDEX_ROW = re.compile(r"^\|\s*(?P<order>[^|]+?)\s*\|(?P<rest>.*)\|\s*$")
STATUS_LINE = re.compile(r"^-\s+\*\*Status:\*\*\s*(?P<status>.+?)\s*$", re.M)
APPLY_LOG_LINE = re.compile(r"\[(?P<id>[^\]]+)\]")


@dataclass(frozen=True)
class Violation:
    """One thing the report says about itself that is not true."""

    rule: str
    detail: str
    finding_id: str = ""

    def __str__(self):
        where = f" [{self.finding_id}]" if self.finding_id else ""
        return f"{self.rule}{where}: {self.detail}"


@dataclass
class IndexRow:
    order: str
    finding_id: str
    status: str
    raw: str

    @property
    def order_number(self):
        """The leading integer of the Order cell, or None.

        The cell may carry a group marker (`2·P`, `2 ▸ primary`), so the number
        is read off the front rather than the whole cell being parsed — the
        marker is for the reader, and the number is the queue position.
        """
        match = re.match(r"\s*(\d+)", self.order)
        return int(match.group(1)) if match else None


@dataclass
class Finding:
    finding_id: str
    status: str


@dataclass
class ConsolidatedReport:
    """What a report claims about itself, parsed once for every rule to read."""

    index_rows: list = field(default_factory=list)
    findings: list = field(default_factory=list)
    apply_log_ids: list = field(default_factory=list)
    has_index: bool = False
    has_apply_log: bool = False

    def finding_by_id(self, finding_id):
        for finding in self.findings:
            if finding.finding_id == finding_id:
                return finding
        return None


def _section(text, heading):
    """The body under one `## heading`, up to the next `## `.

    The heading is matched EXACTLY to the end of its line. Prefix-matching put
    the whole of `## Findings index` under a search for `## Findings`, so the
    body parse came back empty and every indexed row looked dangling -- a
    failure that reads as "the report is broken" when the report was fine.
    """
    match = re.search(rf"^## {re.escape(heading)}\s*$", text, re.M)
    if not match:
        return ""
    start = match.end()
    following = re.search(r"^## ", text[start:], re.M)
    return text[start : start + following.start()] if following else text[start:]


def parse_report(text):
    """Markdown in, a model out. The only function that knows the format.

    Everything below reads the model, so a template reword changes this function
    and nothing else -- which is the point, since the template is edited far more
    often than the rules are.
    """
    report = ConsolidatedReport()

    index = _section(text, "Findings index")
    report.has_index = bool(index.strip())
    for line in index.splitlines():
        row = INDEX_ROW.match(line.strip())
        if not row:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        identifier = FINDING_ID.search(line)
        if not identifier:
            continue  # header or separator row
        report.index_rows.append(
            IndexRow(
                order=cells[0],
                finding_id=identifier.group(0),
                status=cells[-1].strip("` "),
                raw=line.strip(),
            )
        )

    findings_body = _section(text, "Findings")
    for block in re.split(r"^#{3,4}\s+", findings_body, flags=re.M)[1:]:
        identifier = FINDING_ID.search(block)
        if not identifier:
            continue
        status = STATUS_LINE.search(block)
        report.findings.append(
            Finding(
                finding_id=identifier.group(0),
                status=status.group("status").strip("` ") if status else "",
            )
        )

    apply_log = _section(text, "Apply log")
    report.has_apply_log = bool(apply_log.strip())
    for line in apply_log.splitlines():
        for match in APPLY_LOG_LINE.finditer(line):
            candidate = FINDING_ID.search(match.group("id"))
            if candidate:
                report.apply_log_ids.append(candidate.group(0))

    return report


# --- Rules. Each takes the parsed report and returns violations. -------------


def every_finding_is_indexed(report):
    """The index is the dashboard, so a finding missing from it is invisible to
    the reader who is using the table instead of the prose."""
    indexed = {row.finding_id for row in report.index_rows}
    return [
        Violation(
            "unindexed-finding",
            "in the report body but missing from the Findings index",
            finding.finding_id,
        )
        for finding in report.findings
        if finding.finding_id not in indexed
    ]


def every_indexed_row_has_a_finding(report):
    """The inverse: a row pointing at nothing sends the reader hunting."""
    present = {finding.finding_id for finding in report.findings}
    return [
        Violation(
            "dangling-index-row",
            "indexed but there is no such finding in the body",
            row.finding_id,
        )
        for row in report.index_rows
        if row.finding_id not in present
    ]


def index_status_matches_the_finding(report):
    """THE stamping rule. The same fact is written twice -- once in the row and
    once on the finding -- so the two drift, and a stale dashboard is worse than
    none: it is read, believed, and wrong."""
    violations = []
    for row in report.index_rows:
        finding = report.finding_by_id(row.finding_id)
        if finding is None or not finding.status:
            continue
        if row.status != finding.status:
            violations.append(
                Violation(
                    "status-drift",
                    f"index says {row.status!r}, the finding says {finding.status!r}",
                    row.finding_id,
                )
            )
    return violations


def statuses_are_from_the_vocabulary(report):
    """An invented status ("in progress", "wontfix") reads fine and means
    nothing to the Outcome synthesis that has to count them."""
    violations = []
    for finding in report.findings:
        if not finding.status:
            violations.append(
                Violation("missing-status", "no Status: line", finding.finding_id)
            )
            continue
        if not any(
            re.match(pattern, finding.status, re.I) for pattern in STATUS_PATTERNS
        ):
            violations.append(
                Violation(
                    "unknown-status",
                    f"{finding.status!r} is not in the canonical vocabulary "
                    "(docs/refactor-workflow.md)",
                    finding.finding_id,
                )
            )
    return violations


def the_apply_order_is_a_queue(report):
    """THE ordering rule.

    The index's Order column is the apply sequence, and a resolved finding sitting
    above an unresolved one means the queue was jumped. That is allowed -- an
    operator may reorder deliberately -- but it must be VISIBLE, because the
    failure it hides is the expensive one: a change applied before the change
    that was supposed to give it a home.
    """
    ordered = [row for row in report.index_rows if row.order_number is not None]
    ordered.sort(key=lambda row: row.order_number)

    def is_resolved(row):
        return row.status.lower().startswith(RESOLVED_STATUSES)

    # One violation per row that was resolved while something above it was not.
    # Reported against the JUMPER, not the row it jumped: the jumper is the edit
    # that actually happened, and it is the one whose reason is missing.
    violations = []
    for jumper in (row for row in ordered if is_resolved(row)):
        blocking = [
            row
            for row in ordered
            if row.order_number < jumper.order_number and not is_resolved(row)
        ]
        if not blocking:
            continue
        first_blocking = blocking[0]
        violations.append(
            Violation(
                "order-jumped",
                f"resolved at order {jumper.order_number} while "
                f"{first_blocking.finding_id} at order "
                f"{first_blocking.order_number} is still "
                f"{first_blocking.status!r} — record the reason in the Apply log "
                "or reorder the index",
                jumper.finding_id,
            )
        )
    return violations


def grouped_members_share_one_order(report):
    """A grouped change is ONE job. Members on different order numbers is the
    shape that gets a group applied in two halves."""
    by_order = {}
    for row in report.index_rows:
        by_order.setdefault(row.order_number, []).append(row)
    violations = []
    for rows in by_order.values():
        groups = {
            re.search(r"group-\d+", row.raw).group(0)
            for row in rows
            if re.search(r"group-\d+", row.raw)
        }
        if len(groups) > 1:
            violations.append(
                Violation(
                    "group-split",
                    f"one order number carries members of {sorted(groups)} — "
                    "a grouped change is one job and shares one order",
                )
            )
    return violations


def applied_findings_have_a_log_line(report):
    """`applied` with no Apply-log line is the claim without the evidence -- and
    that clause is what makes "a safe refactor actually ran" observable after the
    fact rather than taken on faith."""
    if not report.has_apply_log:
        return []
    logged = set(report.apply_log_ids)
    return [
        Violation(
            "unlogged-apply",
            "status is applied but no Apply-log line names it",
            finding.finding_id,
        )
        for finding in report.findings
        if finding.status.lower().startswith("applied")
        and finding.finding_id not in logged
    ]


def logged_findings_are_not_still_pending(report):
    """The other direction, and the commonest stamping miss: the work happened,
    the log records it, and the Status line was never moved."""
    violations = []
    for finding_id in set(report.apply_log_ids):
        finding = report.finding_by_id(finding_id)
        if finding is not None and finding.status.lower() == "pending":
            violations.append(
                Violation(
                    "stale-pending",
                    "the Apply log records an attempt but the Status is still "
                    "pending — stamp it",
                    finding_id,
                )
            )
    return violations


DEFAULT_RULES = (
    every_finding_is_indexed,
    every_indexed_row_has_a_finding,
    index_status_matches_the_finding,
    statuses_are_from_the_vocabulary,
    the_apply_order_is_a_queue,
    grouped_members_share_one_order,
    applied_findings_have_a_log_line,
    logged_findings_are_not_still_pending,
)


def check_report(text, rules=DEFAULT_RULES):
    """Every violation the given rules find, in rule order."""
    report = parse_report(text)
    if not report.has_index:
        return [
            Violation(
                "no-index",
                "the report has no Findings index — the dashboard is the one "
                "section a reader scans first",
            )
        ]
    return [violation for rule in rules for violation in rule(report)]


def progress_line(report):
    """`3 of 9 findings resolved · 5 pending · 1 deferred` — the one-line state.

    Cheap to compute and the thing a reader wants before anything else, so the
    report carries it rather than making them count rows.
    """
    total = len(report.index_rows)
    resolved = len(
        [
            row
            for row in report.index_rows
            if row.status.lower().startswith(("applied", "failed"))
        ]
    )
    skipped = len(
        [row for row in report.index_rows if row.status.lower().startswith("skipped")]
    )
    deferred = len(
        [row for row in report.index_rows if row.status.lower().startswith("deferred")]
    )
    pending = total - resolved - skipped - deferred
    parts = [f"{resolved} of {total} applied"]
    for count, label in (
        (pending, "pending"),
        (deferred, "deferred"),
        (skipped, "skipped"),
    ):
        if count:
            parts.append(f"{count} {label}")
    return " · ".join(parts)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Check a consolidated report against its own Findings index."
    )
    parser.add_argument("report", help="Path to the consolidated Markdown report.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero on any violation (for a hook or CI). Without it the "
        "run reports and exits 0, because a report mid-apply is legitimately "
        "inconsistent for as long as one edit takes.",
    )
    arguments = parser.parse_args(argv)

    path = Path(arguments.report)
    if not path.is_file():
        print(f"no such report: {path}", file=sys.stderr)
        return 2
    text = path.read_text(encoding="utf-8")
    violations = check_report(text)
    print(progress_line(parse_report(text)))
    for violation in violations:
        print(f"  ✗ {violation}")
    if not violations:
        print("  ✓ index, statuses and apply order agree")
    return 1 if violations and arguments.strict else 0


if __name__ == "__main__":
    import report_index

    sys.exit(report_index.main())
