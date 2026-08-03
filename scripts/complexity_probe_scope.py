"""Turning a scope argument into paths.

Separate from the probe because "which files are in play" changes for reasons
that have nothing to do with how a file is measured — a new scope form, a
different VCS. `--scope` keeps the same vocabulary as scripts/mutation_gate.py
so the two sensors are asked for a target the same way.

Git queries for scope resolution delegate to mutation_gate_scope.changed_paths()
so both probes answer "what changed?" identically. This shared implementation
ensures that untracked files are included in working-tree, that merge-base
errors surface rather than silently producing empty lists, and that future VCS
changes affect both sensors the same way.

A target the *caller* named is refused when it cannot mean anything, because
"I measured nothing" and "there was nothing to measure" are different facts and
only the first belongs to a target that exists. Every caller-named form is
covered — a bare path, a range, several literal paths, and the repo root the
three vocabulary words resolve through — as is a range that begins past its
file's last line.

Two things are deliberately not refused. A path list that came back from git:
a deleted file legitimately appears in a diff. And a file whose length cannot
be read: an unreadable file already reaches the user as `unverified` from the
probe itself, with the read error named.

The caller turns a refusal into an `unverified` measurement carrying the cause.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from mutation_gate_scope import changed_paths

WORKING_TREE = "working-tree"
MERGE_BASE = "merge-base"
FULL = "full"

# "path:40-120" — requires a digit-hyphen-digit tail so a Windows drive letter
# or a bare colon in a path is not mistaken for a range.
_RANGE_PATTERN = re.compile(r"^(?P<path>.+):(?P<start>\d+)-(?P<end>\d+)$")


@dataclass(frozen=True)
class ScopeSelection:
    paths: tuple[str, ...]
    line_range: tuple[int, int] | None
    description: str

    @classmethod
    def of_literal_paths(cls, paths) -> ScopeSelection:
        """Paths a caller named outright, which never reach `resolve_scope`.

        Here rather than at the call site so every phrasing a report can show
        is worded in one module: describing a selection is this file's job even
        for the one form it does not resolve.
        """
        named = tuple(paths)
        return cls(paths=named, line_range=None, description=", ".join(named))


def parse_range(argument: str):
    """Returns (path, start_line, end_line), or None when not a range."""
    match = _RANGE_PATTERN.match(argument)
    if not match:
        return None
    start_line = int(match.group("start"))
    end_line = int(match.group("end"))
    if start_line > end_line:
        return None
    return match.group("path"), start_line, end_line


class LocalFilesystem:
    """The three filesystem questions scope resolution asks: is this a
    directory, is it there at all, and how many lines does it have?

    A collaborator rather than bare `Path(...)` calls for the same reason
    `GitRunner` is one — resolution is then testable without laying down real
    files, and a caller that resolves against something other than the local
    disk has a seam to substitute.

    Narrow on purpose. This is scope resolution's view of a filesystem, not a
    general one: three questions, one client, and every one of them asked to
    decide whether a named target can mean anything.
    """

    def is_directory(self, path) -> bool:
        return Path(path).is_dir()

    def exists(self, path) -> bool:
        return Path(path).exists()

    def line_count(self, path) -> int | None:
        """How many lines `path` holds, or `None` when that cannot be told.

        `None` rather than an exception, because "I could not read this file"
        must not become a refusal: an unreadable file already reaches the user
        as `unverified` from the probe itself, with the read error named. Only
        a definite count is grounds for saying a range names nothing.

        Read as bytes so an encoding a text read would choke on is a line
        count like any other.
        """
        try:
            with open(path, "rb") as handle:
                return sum(1 for _line in handle)
        except OSError:
            return None


class GitRunner:
    """Reuses the mutation gate's scope resolution so both sensors answer
    'what changed?' identically. Untracked files are included in working-tree,
    and errors surface rather than silently becoming empty lists."""

    def __init__(self, repo_root="."):
        self._repo_root = repo_root

    def changed_paths(self, mode: str) -> list[str]:
        return list(changed_paths(self._repo_root, mode))


def _refuse_missing_paths(paths, filesystem) -> None:
    """Raise when a path the caller named outright is not there.

    Only ever applied to paths a *user* named. A path list that came back from
    git is left alone on purpose: a deleted file legitimately appears in a
    diff, and refusing the whole run over an ordinary deletion would be a worse
    failure than the one this guard exists to stop.

    Every missing path is named, not just the first, so a caller who mistyped
    two of them learns about both in one run.
    """
    missing = [path for path in paths if not filesystem.exists(path)]
    if missing:
        named = ", ".join(repr(path) for path in missing)
        raise ValueError(f"no such path: {named}")


def _refuse_a_range_past_the_end(path, start_line, end_line, filesystem) -> None:
    """Raise when a range begins after the file's last line.

    Only when it *begins* past the end. A range that merely overhangs — line 3
    to line 9000 of a forty-line file — is the ordinary "from here to the end"
    gesture and selects real lines, so it narrows as usual. Refusing that would
    reproduce this guard's own failure in the other direction: hiding a target
    the caller was pointing straight at.

    A file whose length cannot be told is not refused. `line_count` returns
    `None` for that, and an unreadable file already reaches the user as
    `unverified` from the probe, with the read error named.
    """
    total_lines = filesystem.line_count(path)
    if total_lines is not None and start_line > total_lines:
        raise ValueError(
            f"{path!r} has {total_lines} line(s), so lines "
            f"{start_line}-{end_line} name nothing"
        )


def resolve_literal_paths(paths, filesystem=None) -> ScopeSelection:
    """The selection for paths a caller named outright, refusing absent ones.

    Separate from `ScopeSelection.of_literal_paths` rather than folded into it:
    a `ScopeSelection` is a value object and has no business holding a
    filesystem. Asking whether a target exists is resolution's job, and
    resolution is where the seam already is.
    """
    disk = filesystem if filesystem is not None else LocalFilesystem()
    named = tuple(paths)
    _refuse_missing_paths(named, disk)
    return ScopeSelection.of_literal_paths(named)


def resolve_scope(
    argument, repo_root=".", git_runner=None, filesystem=None
) -> ScopeSelection:
    resolver = git_runner if git_runner is not None else GitRunner(repo_root)
    disk = filesystem if filesystem is not None else LocalFilesystem()

    if argument is None or argument in (WORKING_TREE, MERGE_BASE, FULL):
        # These three, and only these three, resolve *through* the repo root —
        # the other forms never look at it. A root that is not there was the
        # last caller-named path answered confidently: `--scope full
        # --repo-root <typo>` reported `ran` with no functions, which is the
        # defect this module exists to refuse, and the two git forms crashed
        # with a `FileNotFoundError` carrying exit 1 — the code reserved for a
        # blocking gate verdict, from a branch that is supposed to be a
        # reporter.
        _refuse_missing_paths((repo_root,), disk)

    if argument is None or argument == WORKING_TREE:
        paths = tuple(resolver.changed_paths(WORKING_TREE))
        return ScopeSelection(
            paths=paths,
            line_range=None,
            description="uncommitted changes in the working tree",
        )

    if argument == MERGE_BASE:
        paths = tuple(resolver.changed_paths(MERGE_BASE))
        return ScopeSelection(
            paths=paths, line_range=None, description="changes on this branch"
        )

    if argument == FULL:
        return ScopeSelection(
            paths=(repo_root,), line_range=None, description="the whole repository"
        )

    parsed_range = parse_range(argument)
    if parsed_range:
        path, start_line, end_line = parsed_range
        if disk.is_directory(path):
            # Line numbers belong to one file. Applied to a tree they were
            # cross-applied to every file under it — lines 1-2 of each, reported
            # as one measurement. Rejecting is the honest answer: `<dir>:1-2`
            # names no target that exists. The caller turns this into an
            # `unverified` measurement carrying the cause.
            raise ValueError(
                f"a line range names one file, but {path!r} is a directory — "
                "name a file, or drop the range to measure the whole tree"
            )
        # After the directory check, so `<dir>:1-2` still gets the answer that
        # names its actual problem rather than a bare "no such path"; before
        # the length check, which has nothing to measure against until the
        # file is known to be there.
        _refuse_missing_paths((path,), disk)
        _refuse_a_range_past_the_end(path, start_line, end_line, disk)
        return ScopeSelection(
            paths=(path,),
            line_range=(start_line, end_line),
            description=f"{path} lines {start_line}-{end_line}",
        )

    _refuse_missing_paths((argument,), disk)
    return ScopeSelection(paths=(argument,), line_range=None, description=argument)
