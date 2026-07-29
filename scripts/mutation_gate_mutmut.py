"""The Python backend: invoke mutmut, parse what it gives back.

Spike 2026-07-29, mutmut 3.6.0 on 3.14.6. Two things shape this module:

1. The config key is `source_paths`; `paths_to_mutate` deprecation-warns.
2. Association is function-level. `mutants/mutmut-stats.json` maps a mutated
   function to the pytest node ids that exercise it — there is no killedBy and
   no per-line mapping, unlike Stryker. So a survivor reads as "a mutant in
   discount() survived; these tests exercise it", which is still enough to name
   a vacuous guard.
"""

import os
import re

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
