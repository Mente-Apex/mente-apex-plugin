"""Assertions that fail when the skill fails (issue #153).

An assertion earns its place by failing when the skill fails. Several did not:
they passed whatever the run did, which is why three 100% scores from the
2026-08-04 batch had to be read cautiously.

The general one was the worst. **Nothing checked that the reviewer stage
overturns the analyzer** — prunes a finding, adjusts a tier, dedupes a
double-filed smell. Every run in that batch did it correctly, and a rubber-stamp
reviewer that changed nothing would have scored identically, which defeats the
entire point of a generator/critic split.

These tests pin the hardened assertions so the discrimination cannot quietly
drain back out of an eval set.
"""

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
EVALS = REPO_ROOT / "evals"

# The three lenses #153 names as affected by the missing reviewer-overturn check.
GENERATOR_CRITIC_SETS = ("clean-architecture", "clean-code", "code-quality")


def load(name):
    return json.loads((EVALS / f"{name}-evals.json").read_text(encoding="utf-8"))


def assertions_of(name):
    return [
        assertion
        for one_eval in load(name)["evals"]
        for assertion in one_eval["assertions"]
    ]


@pytest.mark.parametrize("name", GENERATOR_CRITIC_SETS)
def test_the_reviewer_is_tested_for_actually_reviewing(name):
    """One shared assertion pattern across all three, as the issue asked."""
    blob = " ".join(assertions_of(name))

    assert "REVIEWER DISCRIMINATION" in blob, f"{name} never tests the critic half"


@pytest.mark.parametrize("name", GENERATOR_CRITIC_SETS)
def test_it_names_what_overturning_looks_like(name):
    """ "The reviewer reviewed" is not checkable. Pruning with a stated reason,
    re-tiering, or merging a double-filed smell is."""
    blob = " ".join(assertions_of(name))

    assert "prunes it with a stated reason" in blob
    assert "re-tiers" in blob


@pytest.mark.parametrize("name", GENERATOR_CRITIC_SETS)
def test_it_says_why_a_rubber_stamp_must_fail(name):
    blob = " ".join(assertions_of(name))

    assert "scores the same as one that verified nothing" in blob


class TestTheFixturesActuallyExerciseTheAssertions:
    """#153's second class: assertions that are correct but whose fixture can
    never reach them."""

    def test_the_code_quality_crash_eval_pins_when_the_analyzer_dies(self):
        """The one code-quality failure in the batch, and it was the eval's
        fault: the run legitimately had the analyzer crash before writing
        anything, so "nothing to reap or keep" was right and the
        draft-preservation assertion was never exercised."""
        crash_eval = next(
            one_eval
            for one_eval in load("code-quality")["evals"]
            if one_eval["id"] == 3
        )

        assert (
            "writes its draft-findings.md successfully and then" in crash_eval["prompt"]
        )
        assert "there IS a draft to preserve" in crash_eval["prompt"]

    def test_the_findings_index_ordering_assertion_can_disagree_with_a_plain_sort(self):
        """In the original scenario the dependency-aware order coincided exactly
        with Critical→Major, so a run that re-derived the order instead of
        reading the index passed identically."""
        blob = " ".join(assertions_of("code-quality"))

        assert "the index order and a plain Critical→Major sort disagree" in blob

    def test_clean_code_has_a_diff_where_nothing_is_wrong(self):
        """Assertion 5 was untestable against its own fixture — that diff
        contains a genuine swallowed-exception bug, so the "nothing wrong"
        branch could never fire. It needed a clean diff, not deleting."""
        clean_diff_evals = [
            one_eval
            for one_eval in load("clean-code")["evals"]
            if "nothing meaningfully wrong" in one_eval["prompt"]
        ]

        assert clean_diff_evals, "no eval can exercise the clean-review branch"
        blob = " ".join(clean_diff_evals[0]["assertions"])
        assert "manufacturing a finding" in blob


class TestRestraintIsRequiredNotJustPermitted:
    def test_test_quality_must_decline_to_flag_boundary_mocks(self):
        """The best judgement in the whole batch was declining to flag
        legitimate repository/mailer mocking while still catching domain-class
        over-mocking. Nothing required it: a run that flagged every boundary
        mock indiscriminately passed all five assertions."""
        blob = " ".join(assertions_of("test-quality"))

        assert "RESTRAINT" in blob
        assert "must fail this eval" in blob

    def test_the_acceptance_lens_must_decline_the_api_contract_finding(self):
        """The same shape one lens over: HTTP status codes are leakage in a
        user-facing scenario and the agreed behaviour when the stakeholder is
        another service."""
        blob = " ".join(assertions_of("acceptance-quality"))

        assert "Does NOT file the API feature's HTTP verbs" in blob


class TestTheSubtleRubricConstraints:
    """#153's "also observed": constraints subtle enough that a lazier run would
    violate them, which both runs honoured and no assertion named."""

    def test_ccp_co_change_is_evidence_not_a_scripted_metric(self):
        blob = " ".join(assertions_of("clean-architecture"))

        assert "rather than scripting a co-change METRIC" in blob

    def test_the_import_graph_is_reused_only_while_it_is_fresh(self):
        blob = " ".join(assertions_of("clean-architecture"))

        assert "only if the tree is unchanged" in blob

    def test_ddd_must_not_conflate_domain_events_with_event_sourcing(self):
        """Closed earlier in this issue's life; pinned here so the whole
        eval-hardening set lives in one place."""
        blob = " ".join(assertions_of("ddd"))

        assert "Rejects the premise" in blob
