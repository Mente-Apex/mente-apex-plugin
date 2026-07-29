"""The Python backend: invoke mutmut, parse what it gives back.

Spike 2026-07-29, mutmut 3.6.0 on 3.14.6. Two things shape this module:

1. The config key is `source_paths`; `paths_to_mutate` deprecation-warns.
2. Association is function-level. `mutants/mutmut-stats.json` maps a mutated
   function to the pytest node ids that exercise it — there is no killedBy and
   no per-line mapping, unlike Stryker. So a survivor reads as "a mutant in
   discount() survived; these tests exercise it", which is still enough to name
   a vacuous guard.
"""

import json
import os
import re
import shutil
import subprocess
import warnings
from pathlib import Path

from mutation_gate import Survivor

RESULT_LINE = re.compile(r"^\s*(?P<mutant>\S+):\s*(?P<status>\w+)\s*$", re.MULTILINE)
MUTANT_SUFFIX = re.compile(r"__mutmut_\d+$")


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
    """
    tests_by_function = stats.get("tests_by_mangled_function_name", {})
    survivors = []
    for match in RESULT_LINE.finditer(results_text):
        if match.group("status") != "survived":
            continue
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
    """
    config_path = Path(repo_root) / "pyproject.toml"
    existing = config_path.read_text(encoding="utf-8") if config_path.is_file() else ""
    entries = ", ".join(json.dumps(path) for path in paths)
    config_path.write_text(
        existing + f"\n[tool.mutmut]\nsource_paths = [{entries}]\n",
        encoding="utf-8",
    )


class MutmutBackend:
    """Invokes mutmut in the scratch workspace and parses what it emits."""

    stack = "python"
    tool = "mutmut"

    def available(self, repo_root):
        return shutil.which("mutmut") is not None

    def install_hint(self, repo_root):
        return "uv add --dev mutmut"

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
        still emit a `not_checked` line per mutant, which is not a result and
        must not be mistaken for a clean zero-survivor run). Checking only
        "no results parsed" would miss exactly that case, so the stats file's
        existence is the one signal trusted here; its absence surfaces the
        run's exit status and stderr via a warning rather than being
        swallowed as silence.
        """
        _configure_source_paths(repo_root, paths)
        run_result = subprocess.run(
            ["mutmut", "run"], cwd=repo_root, capture_output=True, text=True
        )
        results_result = subprocess.run(
            ["mutmut", "results"], cwd=repo_root, capture_output=True, text=True
        )
        stats_path = Path(repo_root) / "mutants" / "mutmut-stats.json"
        if not stats_path.is_file():
            warnings.warn(
                f"mutmut never wrote {stats_path} in {repo_root} -- its "
                "baseline stats collection did not complete, so any results "
                "below are incomplete, not a clean zero-survivor run "
                f"(`mutmut run` exit {run_result.returncode}: "
                f"{run_result.stderr.strip() or run_result.stdout.strip()!r}; "
                f"`mutmut results` exit {results_result.returncode}: "
                f"{results_result.stdout.strip()!r})",
                stacklevel=2,
            )
        stats = (
            json.loads(stats_path.read_text(encoding="utf-8"))
            if stats_path.is_file()
            else {}
        )
        return survivors_from_output(
            results_result.stdout, stats, diffs={}, source_paths=paths
        )
