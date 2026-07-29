"""The /test-quality mutation gate.

"Suite still green" proves nothing when the thing you changed is the test, so
this runs real mutation testing: change the code under test mechanically and
see whether the suite notices. mutmut and Stryker do their own mutating, so a
backend's job is `survivors(selection)` — how it gets them is its business.
"""

from dataclasses import dataclass

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


@dataclass(frozen=True)
class GateResult:
    """What one gate run produced.

    No score field, deliberately. A percentage gets gamed and tells an operator
    nothing; the survivors and their associated tests are the whole signal.
    """

    survivors: tuple
    unavailable: tuple
    unresolved: tuple


def run_gate(repo_root, paths, backends):
    """Partition the selection, invoke each backend once, merge the results.

    A backend whose partition is empty is never invoked — a repo with no JS is
    simply a run where the Stryker partition is empty, not a failure. A backend
    whose tool is missing yields an install hint and the run continues: the gate
    never installs anything on the operator's behalf, and a missing tool
    degrades a run rather than failing it.
    """
    partitions = partition(paths)
    survivors = []
    unavailable = []
    for backend in backends:
        selection = partitions.get(backend.stack, ())
        if not selection:
            continue
        if not backend.available(repo_root):
            unavailable.append((backend.stack, backend.install_hint(repo_root)))
            continue
        survivors.extend(backend.survivors(repo_root, selection))
    return GateResult(
        survivors=tuple(survivors),
        unavailable=tuple(unavailable),
        unresolved=partitions.get("unresolved", ()),
    )
