"""The Python backend: invoke mutmut, parse what it gives back.

Spike 2026-07-29, mutmut 3.6.0 on 3.14.6. Two things shape this module:

1. The config key is `source_paths`; `paths_to_mutate` deprecation-warns.
2. Association is function-level. `mutants/mutmut-stats.json` maps a mutated
   function to the pytest node ids that exercise it — there is no killedBy and
   no per-line mapping, unlike Stryker. So a survivor reads as "a mutant in
   discount() survived; these tests exercise it", which is still enough to name
   a vacuous guard.
"""

import re

from mutation_gate import Survivor

RESULT_LINE = re.compile(r"^\s*(?P<mutant>\S+):\s*(?P<status>\w+)\s*$", re.MULTILINE)
MUTANT_SUFFIX = re.compile(r"__mutmut_\d+$")


def _function_of(mutant_name):
    """`money.x_discount__mutmut_1` -> `money.x_discount`."""
    return MUTANT_SUFFIX.sub("", mutant_name)


def survivors_from_output(results_text, stats, diffs):
    """Turn `mutmut results` + mutmut-stats.json into Survivors."""
    tests_by_function = stats.get("tests_by_mangled_function_name", {})
    survivors = []
    for match in RESULT_LINE.finditer(results_text):
        if match.group("status") != "survived":
            continue
        mutant = match.group("mutant")
        function = _function_of(mutant)
        survivors.append(
            Survivor(
                artifact=function.split(".")[0],
                location=function,
                mutant=mutant,
                mutant_diff=diffs.get(mutant, ""),
                associated_tests=tuple(tests_by_function.get(function, ())),
                backend="mutmut",
                granularity="function",
            )
        )
    return tuple(survivors)
