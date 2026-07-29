"""The /test-quality mutation gate.

"Suite still green" proves nothing when the thing you changed is the test, so
this runs real mutation testing: change the code under test mechanically and
see whether the suite notices. mutmut and Stryker do their own mutating, so a
backend's job is `survivors(selection)` — how it gets them is its business.
"""

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from mutation_gate_workspace import scratch_workspace

PYTHON_SUFFIXES = (".py",)
JS_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
PROSE_SUFFIXES = (".md",)


@dataclass(frozen=True)
class Survivor:
    """One mutant the suite failed to kill.

    `granularity` records what the backend could actually tell us — Stryker
    resolves a survivor to a line and the tests that covered it, mutmut only to
    the mutated function. The report states which, rather than implying a
    precision the backend never had.
    """

    artifact: str
    location: str
    mutant: str
    associated_tests: tuple[str, ...]
    backend: str
    granularity: str
    mutant_diff: str = ""
    status: str = "survived"


def partition(paths):
    """Group paths by the backend that owns them.

    Dispatch is per partition, not per test: mutmut and Stryker are invoked
    over a file set, and a per-test invocation loop would be ruinously slow.
    """
    partitions = {"python": [], "js": [], "prose": [], "unresolved": []}
    for path in paths:
        if path.endswith(PYTHON_SUFFIXES):
            partitions["python"].append(path)
        elif path.endswith(JS_SUFFIXES):
            partitions["js"].append(path)
        elif path.endswith(PROSE_SUFFIXES):
            partitions["prose"].append(path)
        else:
            partitions["unresolved"].append(path)
    return {stack: tuple(paths) for stack, paths in partitions.items()}


# The stacks a backend may legitimately claim. "unresolved" is not one of
# them: it is partition()'s catch-all for suffixes no stack owns, never a
# stack a backend registers against.
REGISTRABLE_STACKS = ("python", "js", "prose")


@runtime_checkable
class Backend(Protocol):
    """A mutation-testing tool for one stack, behind a uniform seam.

    mutmut and Stryker (and any future backend) implement this without
    inheriting from it — `run_gate` only ever calls through the protocol, so
    adding a fourth backend is registering an object, not editing a dispatch
    chain.
    """

    stack: str
    tool: str

    def available(self, repo_root) -> bool: ...

    def install_hint(self, repo_root) -> str: ...

    def survivors(self, repo_root, paths) -> tuple:  # tuple[Survivor, ...]
        ...


@dataclass(frozen=True)
class GateResult:
    """What one gate run produced.

    No score field, deliberately. A percentage gets gamed and tells an operator
    nothing; the survivors and their associated tests are the whole signal.

    `unresolved` and `unclaimed` are deliberately separate: `unresolved` is a
    file whose suffix matches no stack at all, `unclaimed` is a file that DID
    land in a known stack partition (python/js/prose) for which no backend was
    registered this run. Conflating them would hide a missing backend behind
    the same label as an image asset — every input path must be accounted for
    in exactly one of survivors / unavailable / unresolved / unclaimed.
    """

    survivors: tuple[Survivor, ...]
    unavailable: tuple[tuple[str, str], ...]
    unresolved: tuple[str, ...]
    unclaimed: tuple[str, ...]


def run_gate(repo_root, paths, backends: list) -> GateResult:
    """Partition the selection, invoke each backend once, merge the results.

    A backend whose partition is empty is never invoked — a repo with no JS is
    simply a run where the Stryker partition is empty, not a failure. A backend
    whose tool is missing yields an install hint and the run continues: the gate
    never installs anything on the operator's behalf, and a missing tool
    degrades a run rather than failing it.

    Two failure modes are misconfiguration, not run-time degradation, and are
    raised eagerly instead of silently tolerated: a backend declaring a stack
    `partition()` never produces (the gate misunderstanding its own data), and
    two backends registered for the same stack (an undefined, silently-merged
    outcome otherwise).
    """
    backends_by_stack = {}
    for backend in backends:
        if backend.stack not in REGISTRABLE_STACKS:
            raise ValueError(
                f"backend {backend.tool!r} declares stack {backend.stack!r}, "
                f"which partition() never produces "
                f"(known stacks: {REGISTRABLE_STACKS})"
            )
        if backend.stack in backends_by_stack:
            raise ValueError(
                f"two backends registered for stack {backend.stack!r}: "
                f"{backends_by_stack[backend.stack].tool!r} and {backend.tool!r}"
            )
        backends_by_stack[backend.stack] = backend

    partitions = partition(paths)
    survivors = []
    unavailable = []
    unclaimed = []
    for stack in REGISTRABLE_STACKS:
        selection = partitions.get(stack, ())
        if not selection:
            continue
        backend = backends_by_stack.get(stack)
        if backend is None:
            unclaimed.extend(selection)
            continue
        if not backend.available(repo_root):
            unavailable.append((stack, backend.install_hint(repo_root)))
            continue
        survivors.extend(backend.survivors(repo_root, selection))
    return GateResult(
        survivors=tuple(survivors),
        unavailable=tuple(unavailable),
        unresolved=partitions.get("unresolved", ()),
        unclaimed=tuple(unclaimed),
    )


def _git(repo_root, *args):
    result = subprocess.run(
        ["git", *args], cwd=repo_root, capture_output=True, text=True, check=True
    )
    return result.stdout


def _default_branch(repo_root):
    """The local default branch, preferring main, falling back to master."""
    branches = _git(repo_root, "branch", "--format=%(refname:short)").split()
    for candidate in ("main", "master"):
        if candidate in branches:
            return candidate
    return branches[0] if branches else "HEAD"


def changed_paths(repo_root, scope="merge-base"):
    """The files this run mutates.

    merge-base is the default because it is stable: an operator committing
    mid-audit should not change what the sweep covers. Full-repo mutation is
    far too slow to be anyone's default in an interactive skill.
    """
    if scope == "merge-base":
        base = _default_branch(repo_root)
        fork_point = _git(repo_root, "merge-base", base, "HEAD").strip()
        output = _git(repo_root, "diff", "--name-only", fork_point, "HEAD")
    elif scope == "working-tree":
        output = _git(repo_root, "status", "--porcelain", "--untracked-files=all")
        output = "\n".join(line[3:] for line in output.splitlines())
    elif scope == "full":
        output = _git(repo_root, "ls-files")
    else:
        raise ValueError(f"unknown scope: {scope!r}")
    return tuple(line for line in output.splitlines() if line)


def main(argv=None):
    """Run the gate and print the result as JSON for the calling agent."""
    parser = argparse.ArgumentParser(description="Run the test-quality mutation gate.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument(
        "--scope", choices=("merge-base", "working-tree", "full"), default="merge-base"
    )
    arguments = parser.parse_args(argv)

    from mutation_gate_report import as_report_payload, default_backends

    paths = changed_paths(arguments.repo_root, scope=arguments.scope)
    with scratch_workspace(arguments.repo_root) as workspace:
        result = run_gate(workspace, paths, default_backends())
    print(json.dumps(as_report_payload(result, scope=arguments.scope), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
