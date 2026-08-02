"""Turning a scope argument into paths.

Separate from the probe because "which files are in play" changes for reasons
that have nothing to do with how a file is measured — a new scope form, a
different VCS. `--scope` keeps the same vocabulary as scripts/mutation_gate.py
so the two sensors are asked for a target the same way.
"""

import re
import subprocess
from dataclasses import dataclass

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


class GitRunner:
    """The git queries scope resolution needs, isolated so tests can stub them."""

    def __init__(self, repo_root="."):
        self._repo_root = repo_root

    def changed_paths(self, mode: str) -> list[str]:
        if mode == MERGE_BASE:
            command = [
                "git",
                "diff",
                "--name-only",
                "--diff-filter=d",
                "origin/HEAD...",
            ]
        else:
            command = ["git", "diff", "--name-only", "--diff-filter=d", "HEAD"]
        completed = subprocess.run(
            command,
            cwd=self._repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        return [line for line in completed.stdout.splitlines() if line.strip()]


def resolve_scope(argument, repo_root=".", git_runner=None) -> ScopeSelection:
    resolver = git_runner if git_runner is not None else GitRunner(repo_root)

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
        return ScopeSelection(
            paths=(path,),
            line_range=(start_line, end_line),
            description=f"{path} lines {start_line}-{end_line}",
        )

    return ScopeSelection(paths=(argument,), line_range=None, description=argument)
