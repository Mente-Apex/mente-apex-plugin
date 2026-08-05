"""Eval sets must be revisited when the skill they grade changes.

#150: `evals/evals.json` asserted on `export` / `merge` / `import` engine
subcommands long after config-sync v0.11.0 replaced them with
`propagate-export` / `consolidate` / `propagate-apply`. The eval run followed
the current skill correctly and was penalised for being right -- four stale
assertions, and the resulting 60% score said nothing about the skill.

Nothing caught it because nothing connected the two files. Each eval set now
declares `reviewed_against_skill_versions`, a map from every skill the set
exercises to the version its assertions were last checked against, and this
module holds that map in lockstep with each skill's own `metadata.version`.
Bumping a skill therefore fails the suite until someone re-reads its evals
and re-stamps them -- the revisit is the point, and the map is the record
that it happened.

A map rather than a single version because a set may grade more than one
skill: `evals.json` exercises `config-sync` for the sync cycle and
`config-sync-setup` for the first-time and join flows, and a lone version
would have left the second one drifting exactly as silently as before.

Deliberately equality, not the floor used for `metadata.version` itself
(see `skill_version_policy`): a floor would let an eval set stamped 0.1.0
sit under a skill at 0.9.0 forever, which is exactly the drift this exists
to stop.
"""

import json
from pathlib import Path

import pytest

from skill_version_policy import parse_metadata_version

REPO_ROOT = Path(__file__).resolve().parents[1]
EVAL_SET_PATHS = sorted((REPO_ROOT / "evals").glob("*.json"))
STAMP = "reviewed_against_skill_versions"


def _identify(eval_set_path):
    """Name a parametrized case by its file rather than a bare index."""
    return eval_set_path.name


@pytest.fixture(params=EVAL_SET_PATHS, ids=_identify)
def eval_set(request):
    """One eval set: its path and its parsed document."""
    eval_set_path = request.param
    return eval_set_path, json.loads(eval_set_path.read_text(encoding="utf-8"))


def _skills_exercised(document):
    """Every skill the set actually runs, not only the one it is named for.

    The top-level `skill_name` names the set; each eval may name a different
    `skill` it dispatches to. Both are graded, so both are held in lockstep.
    """
    exercised = {document["skill_name"]}
    exercised.update(
        single_eval["skill"]
        for single_eval in document["evals"]
        if single_eval.get("skill")
    )
    return exercised


def _current_version(skill_name):
    skill_md = REPO_ROOT / "skills" / skill_name / "SKILL.md"
    assert (
        skill_md.is_file()
    ), f"no {skill_md.relative_to(REPO_ROOT)} for {skill_name!r}"
    return ".".join(
        str(part)
        for part in parse_metadata_version(skill_md.read_text(encoding="utf-8"))
    )


def test_at_least_one_eval_set_is_discovered():
    """A glob that silently matched nothing would make every case below vacuous."""
    assert EVAL_SET_PATHS


def test_every_exercised_skill_is_stamped(eval_set):
    eval_set_path, document = eval_set
    stamped = set(document.get(STAMP, {}))

    unstamped = _skills_exercised(document) - stamped
    assert not unstamped, (
        f"{eval_set_path.name} exercises {sorted(unstamped)} but does not stamp "
        f"{STAMP} for them; add each with the skill version whose behaviour "
        "these assertions match"
    )


def test_no_stamp_names_a_skill_the_set_never_exercises(eval_set):
    """A stamp for an unexercised skill is a lockstep assertion nothing backs."""
    eval_set_path, document = eval_set

    stray = set(document.get(STAMP, {})) - _skills_exercised(document)
    assert (
        not stray
    ), f"{eval_set_path.name} stamps {sorted(stray)}, which no eval in it runs"


def test_every_stamp_is_in_lockstep_with_its_skill(eval_set):
    eval_set_path, document = eval_set

    drifted = {
        skill_name: (reviewed, _current_version(skill_name))
        for skill_name, reviewed in document.get(STAMP, {}).items()
        if reviewed != _current_version(skill_name)
    }
    assert not drifted, (
        f"{eval_set_path.name} has drifted: "
        + "; ".join(
            f"{skill_name} was last reviewed at {reviewed}, now at {current}"
            for skill_name, (reviewed, current) in sorted(drifted.items())
        )
        + ". Re-read the assertions against the shipped skill, fix what drifted, "
        f"then update {STAMP}."
    )
