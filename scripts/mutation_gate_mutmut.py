"""The Python backend: invoke mutmut, parse what it gives back.

Spike 2026-07-29, mutmut 3.6.0 on 3.14.6. Two things shape this module:

1. The config key is `source_paths`; `paths_to_mutate` deprecation-warns.
2. Association is function-level. `mutants/mutmut-stats.json` maps a mutated
   function to the pytest node ids that exercise it — there is no killedBy and
   no per-line mapping, unlike Stryker. So a survivor reads as "a mutant in
   discount() survived; these tests exercise it", which is still enough to name
   a vacuous guard.

Status handling, fix round 2: verified against `status_by_exit_code` in the
installed mutmut 3.6.0's `mutmut/__main__.py`. The full vocabulary is
`killed`, `survived`, `skipped`, `suspicious`, `timeout`, `segfault` (single
word) and `no tests`, `not checked`, `caught by type check`, `check was
interrupted by user` (space-separated, multi-word). `RESULT_LINE` used to
match only word characters, so the multi-word statuses never matched at all, and
`survivors_from_output` used to keep only `status == "survived"`, silently
dropping every other single-word status too -- exactly the silence this gate
exists to prevent. `killed` is now the only status silently dropped, as the
clean success case; every other recognised status becomes a Survivor whose
`status` names it, landing in the report's Inconclusive section like
Stryker's non-Survived statuses. A status this module has never seen raises,
matching `mutation_gate_stryker.py`'s ruling: an unrecognised status means the
parser misunderstands its own data source, not a missing tool.

Status handling, fix round 3: round 2, taken alone, turned a *different*
existing failure mode into a flood. When `mutants/mutmut-stats.json` was
never written -- collection crashed before a single mutant executed --
`mutmut results` can still print a `not checked` line per mutant it would
have run. That is ONE fact about the run (it never completed), not N facts
about N mutants, but round 2's per-line parsing reported it as N Survivors
(reproduced live: 4298 of them, all `not checked`, on a single crashed run).
`MutmutBackend.survivors()` now treats the missing stats file as what it
already was known to mean (see its own docstring) and reports it once via
`run_errors()` instead of handing the per-mutant lines to
`survivors_from_output` at all. `survivors_from_output` itself is unchanged:
a completed run's genuine per-mutant `not checked`/`timeout`/etc. results (a
real, if rare, outcome even when collection succeeds) still flow through
individually -- the stats file's presence is what tells the two cases apart,
exactly as it already did before this fix existed.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
import warnings
from pathlib import Path

from mutation_gate import Survivor
from mutation_gate_freshness import ReportFreshness

RESULT_LINE = re.compile(r"^\s*(?P<mutant>\S+):\s*(?P<status>.+?)\s*$", re.MULTILINE)

# Bounded like every other subprocess the gate starts: `mutmut run` drives the
# audited repo's suite once per mutant, which is arbitrary code and may hang.
RUN_TIMEOUT_SECONDS = 1800


def _stats_path(repo_root):
    """mutmut's baseline stats file, as a one-element candidate list.

    Written during collection, before a single mutant executes, which is what
    makes it the signal that a run got that far. Shaped as a sequence because
    `ReportFreshness` takes a discovery strategy rather than a single path.
    """
    return (Path(repo_root) / "mutants" / "mutmut-stats.json",)


def _scope_notes_for(repo_root, paths):
    """Say so when this run will cover something other than the selection.

    `_configure_source_paths` deliberately leaves a repo's own
    `[tool.mutmut]` table alone, so mutmut then mutates that table's
    `source_paths` rather than the paths the gate selected. The run completes
    and its per-mutant results are real -- this is a scope caveat, not a run
    error -- but staying silent about it let a survivor-free result over
    somebody else's scope read exactly like a clean result over yours.
    """
    config_path = Path(repo_root) / "pyproject.toml"
    if not config_path.is_file():
        return ()
    try:
        parsed = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError, OSError:
        return ()
    if "mutmut" not in parsed.get("tool", {}):
        return ()
    return (
        "mutmut ran under the repo's own [tool.mutmut] source_paths, so it "
        f"mutated those rather than the {len(paths)} selected path(s); "
        "results cover the repo's configured scope, not the selection",
    )


MUTANT_SUFFIX = re.compile(r"__mutmut_\d+$")

KILLED_STATUS = "killed"
SURVIVED_STATUS = "survived"

# Every status mutmut 3.6.0 emits, verified against `status_by_exit_code` in
# the installed `mutmut/__main__.py`. `killed` and `survived` are handled by
# name above; everything else here is neither a kill nor a clean survival --
# each becomes a Survivor carrying this exact status. Anything not in this
# set (nor `killed`/`survived`) is unrecognised and raises.
KNOWN_INCONCLUSIVE_STATUSES = frozenset(
    {
        "skipped",
        "suspicious",
        "timeout",
        "segfault",
        "no tests",
        "not checked",
        "caught by type check",
        "check was interrupted by user",
    }
)


def _function_of(mutant_name):
    """`money.x_discount__mutmut_1` -> `money.x_discount`."""
    return MUTANT_SUFFIX.sub("", mutant_name)


def _module_name_of(source_path):
    """Compute the module name mutmut would derive for a source path.

    Mirrors mutmut's own key construction (`get_mutant_name`): the relative
    path with `.py` stripped, `os.sep` (and `/`, since fixtures and mutmut
    keys both use it regardless of platform) replaced by `.`, and a leading
    `src.` package component stripped.
    """
    module = source_path
    if module.endswith(".py"):
        module = module[: -len(".py")]
    module = module.replace(os.sep, ".").replace("/", ".")
    if module.startswith("src."):
        module = module[len("src.") :]
    return module


def _resolve_artifact(function, source_paths):
    """Resolve a mutmut module+function key to the real source path.

    mutmut's key only carries the dotted module name, and that alone is
    genuinely ambiguous — `api.money` could be `api/money.py` or
    `api/money/__init__.py`, and naming just the first dotted segment (the
    previous approach) was outright wrong: it named a directory as if it were
    a file, and did so inconsistently with the Stryker backend's real file
    paths. Resolving against the actual paths the backend was invoked over
    removes the ambiguity. The longest matching module name wins, because a
    deeper module is always a more specific match than one of its own
    package's shorter prefixes.

    When nothing in the selection matches — the backend was invoked without a
    selection, or the mutant's module isn't in it — degrade to a dotted-path
    approximation rather than crash or silently emit a directory name, so the
    field stays path-shaped and consistent with Stryker either way.
    """
    best_path = None
    best_module_len = -1
    for source_path in source_paths:
        module = _module_name_of(source_path)
        matches = function == module or function.startswith(module + ".")
        if matches and len(module) > best_module_len:
            best_module_len = len(module)
            best_path = source_path
    if best_path is not None:
        return best_path
    return function.rsplit(".", 1)[0].replace(".", "/") + ".py"


def survivors_from_output(results_text, stats, diffs, source_paths=()):
    """Turn `mutmut results` + mutmut-stats.json into Survivors.

    `source_paths` is the selection the backend invoked mutmut over — the same
    `paths` a `MutmutBackend.survivors(repo_root, paths)` receives — used only
    to resolve each survivor's `artifact` back to a real file path.

    `killed` is the only status silently dropped -- the clean success case.
    `survived` becomes an ordinary Survivor. Every other recognised status
    (see `KNOWN_INCONCLUSIVE_STATUSES`) also becomes a Survivor, but carrying
    its own `status`, so it reaches the operator as inconclusive rather than
    vanishing. A status this module has never seen raises, exactly as
    `mutation_gate_stryker.py`'s `survivors_from_report` does for an
    unrecognised Stryker status.
    """
    tests_by_function = stats.get("tests_by_mangled_function_name", {})
    survivors = []
    for match in RESULT_LINE.finditer(results_text):
        raw_status = match.group("status")
        if raw_status == KILLED_STATUS:
            continue
        if (
            raw_status != SURVIVED_STATUS
            and raw_status not in KNOWN_INCONCLUSIVE_STATUSES
        ):
            raise ValueError(
                f"unrecognized mutmut mutant status {raw_status!r} for mutant "
                f"{match.group('mutant')!r}; KNOWN_INCONCLUSIVE_STATUSES needs "
                "updating"
            )
        mutant = match.group("mutant")
        function = _function_of(mutant)
        survivors.append(
            Survivor(
                artifact=_resolve_artifact(function, source_paths),
                location=function,
                mutant=mutant,
                mutant_diff=diffs.get(mutant, ""),
                associated_tests=tuple(tests_by_function.get(function, ())),
                backend="mutmut",
                granularity="function",
                status=raw_status,
            )
        )
    return tuple(survivors)


def _configure_source_paths(repo_root, paths):
    """Write `[tool.mutmut] source_paths` into the workspace's pyproject.toml.

    mutmut's config loader (`_config_reader`) tries pyproject.toml's
    `[tool.mutmut]` table first, and only falls back to setup.cfg's `[mutmut]`
    section when that table is absent entirely -- so this is the one mutmut
    actually reads. Without it, mutmut's own `_guess_source_paths` runs, and on
    a repo shaped like this one (no `lib/`, `src/`, or package dir matching the
    repo name) it raises `FileNotFoundError` before mutating anything, which is
    why the CLI was observed to fail with no `[mutmut] source_paths` configured
    during the Task 3 spike. Deriving it from the real selection, rather than
    hand-configuring a fixed source tree once, keeps it correct as the
    partition mutmut is invoked over changes run to run.

    Parsed first, not appended blind: a repo that already configures mutmut
    itself (a `[tool.mutmut]` table of its own in pyproject.toml) would
    otherwise end up with two `[tool.mutmut]` tables after this runs, which is
    invalid TOML and corrupts the workspace's copy of the file. Where that
    table already exists, it is left exactly as the operator wrote it --
    respecting a real configuration decision beats overriding it with a
    derived one, and mutmut's own loader already prefers a `source_paths` an
    operator set.
    """
    config_path = Path(repo_root) / "pyproject.toml"
    existing = config_path.read_text(encoding="utf-8") if config_path.is_file() else ""
    if existing:
        parsed = tomllib.loads(existing)
        if "mutmut" in parsed.get("tool", {}):
            return
    entries = ", ".join(json.dumps(path) for path in paths)
    config_path.write_text(
        existing + f"\n[tool.mutmut]\nsource_paths = [{entries}]\n",
        encoding="utf-8",
    )


def _mutmut_executable():
    """Resolve the mutmut console script the same way it will actually run.

    `shutil.which("mutmut")` depends entirely on the *current* process's
    PATH, which only carries `.venv/bin` because the documented invocation
    (`uv run python scripts/mutation_gate.py`) happens to put it there --
    nothing enforced or even checked that contract, so a bare
    `python3 scripts/mutation_gate.py` would see PATH without `.venv/bin`,
    report mutmut as unavailable, and silently skip the whole Python
    partition with a misleading "install it" hint for a tool that is, in
    fact, already installed. `sys.executable` names the real interpreter
    running this process regardless of PATH, and mutmut's own console script
    lives right beside it in the same uv-managed venv's `bin/` -- resolving
    there first makes availability match how `survivors()` actually invokes
    the tool. PATH is kept as a fallback for a mutmut installed some other
    way (e.g. `uv tool install`), so this only adds a check, never removes
    one.
    """
    sibling = Path(sys.executable).with_name("mutmut")
    if sibling.is_file():
        return str(sibling)
    return shutil.which("mutmut")


class MutmutBackend:
    """Invokes mutmut in the scratch workspace and parses what it emits."""

    stack = "python"
    tool = "mutmut"

    def __init__(self, freshness=None):
        self._run_errors = ()
        self._mutants_executed = None
        self._scope_notes = ()
        # Injected for the same reason StrykerBackend's is: the before/after
        # freshness policy is shared, and a test substitutes a trivial
        # discovery strategy rather than manipulating mtimes on disk.
        self._freshness = freshness or ReportFreshness(_stats_path)

    def available(self, repo_root):
        return _mutmut_executable() is not None

    def install_hint(self, repo_root):
        return "uv add --dev mutmut"

    def run_errors(self, repo_root):
        """Run-level facts from the most recent `survivors()` call.

        Empty unless that call's collection crashed before writing
        `mutants/mutmut-stats.json` -- see `survivors()`. Distinct from a
        completed run's genuine per-mutant inconclusive results, which stay
        in `survivors()`'s return value as ordinary `Survivor`s instead.
        """
        return self._run_errors

    def scope_notes(self, repo_root):
        """What this run actually covered, when that is not the selection.

        See `_scope_notes_for`. Implemented here for the same reason
        `PitestBackend` implements it: a backend that silently runs a
        different scope than the one it was handed is a Liskov break the gate
        cannot detect, and this is the channel that makes it visible.
        """
        return self._scope_notes

    def mutants_executed(self, repo_root):
        """How many mutants the most recent `survivors()` call accounted for.

        `None` when the run did not complete, so the gate reports the count as
        unanswered rather than as a truthful zero.
        """
        return self._mutants_executed

    def survivors(self, repo_root, paths):
        """Run mutmut over `paths` in the (already-isolated) workspace.

        `paths` is forwarded to `survivors_from_output` as `source_paths` so
        each survivor's `artifact` resolves to a real file path rather than
        the dotted-module approximation `_resolve_artifact` falls back to
        when it has nothing to match against.

        mutmut's own exit code is not a failure signal by itself -- it exits
        non-zero whenever a mutant survives, which is the normal, common case,
        not a tool failure. But `mutants/mutmut-stats.json` is written as part
        of mutmut's baseline stats collection, which happens before a single
        mutant is ever executed -- so its absence is unconditionally a sign
        the run never got past collection, whether or not `mutmut results`
        still printed something (observed in practice: a collection crash can
        still emit a `not checked` line per mutant it would have run). That is
        one fact about the run, not one fact per mutant it never got to check,
        so this method does not hand those lines to `survivors_from_output` at
        all in that case -- it reports the crash once via `self._run_errors`
        (read back through `run_errors()`) and returns no survivors from this
        call. When the stats file IS present, the run completed and its real
        per-mutant statuses (including any genuine `not checked` outcome that
        can still occur even in a completed run) flow through
        `survivors_from_output` exactly as fix round 2 established.

        The stats file's PRESENCE, though, is not the converse of its absence,
        and treating it as such reopened the hole from the inside: `mutants/`
        is gitignored, so `--scope working-tree` copies the operator's
        previous run's cache into the workspace. A `mutmut run` that then
        crashed during collection left a stale `mutmut-stats.json` sitting
        exactly where `is_file()` looked, and `mutmut results` replayed the
        previous run's cached statuses -- a prior all-killed cache rendering
        as a clean pass. So the test is whether THIS run wrote the file, not
        whether the file is there.
        """
        self._scope_notes = _scope_notes_for(repo_root, paths)
        _configure_source_paths(repo_root, paths)
        executable = _mutmut_executable()
        self._freshness.snapshot(repo_root)
        try:
            run_result = subprocess.run(
                [executable, "run"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=RUN_TIMEOUT_SECONDS,
            )
            results_result = subprocess.run(
                [executable, "results"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=RUN_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            self._mutants_executed = None
            self._run_errors = (
                f"mutmut did not finish within {RUN_TIMEOUT_SECONDS}s in "
                f"{repo_root}, so no result from this partition can be trusted",
            )
            warnings.warn(self._run_errors[0], stacklevel=2)
            return ()

        if not self._freshness.written_since(repo_root):
            not_checked_count = len(RESULT_LINE.findall(results_result.stdout))
            summary = (
                f"mutmut run did not complete in {repo_root} -- this run wrote "
                f"no {_stats_path(repo_root)[0].name}, so its baseline stats "
                "collection never finished and no per-mutant result below is "
                f"real ({not_checked_count} mutant"
                f"{'' if not_checked_count == 1 else 's'} not checked as a "
                "consequence). Any stats file already present is from an "
                "earlier run and was NOT read"
            )
            # Real newlines, never repr(): this string is the analyzer's full-
            # detail channel (surfaced verbatim in the JSON payload), but a
            # repr() here would turn every newline into a literal backslash-n,
            # collapsing a multi-KB traceback into one unreadable line for
            # every consumer downstream, including render_markdown's own
            # line-based bounding.
            run_output = run_result.stderr.strip() or run_result.stdout.strip()
            results_output = results_result.stdout.strip()
            self._run_errors = (
                f"{summary}\n"
                f"`mutmut run` exit {run_result.returncode}:\n"
                f"{run_output}\n"
                f"`mutmut results` exit {results_result.returncode}:\n"
                f"{results_output}",
            )
            warnings.warn(self._run_errors[0], stacklevel=2)
            self._mutants_executed = None
            return ()
        self._run_errors = ()
        stats = json.loads(_stats_path(repo_root)[0].read_text(encoding="utf-8"))
        # Every result line mutmut printed is one mutant it accounted for,
        # whatever its status -- the number that tells "all fifty killed" apart
        # from "zero generated", which an empty survivor list cannot.
        self._mutants_executed = len(RESULT_LINE.findall(results_result.stdout))
        return survivors_from_output(
            results_result.stdout, stats, diffs={}, source_paths=paths
        )
