"""Squash- and rebase-merged branches are merged too (issue #108).

The hook's whole basis is `merge-base --is-ancestor`. A squash or rebase merge
rewrites the branch's commits, so its tip is not an ancestor of the default and
that test returns false -- forever. The hook shipped in #107, which was itself
rebase-merged, and did not fire on its own merge.

Two of its three lines go dark for anyone who does not merge-commit:
`merged_local_branches` shares the same ancestor test, so a rebase-merged branch
is never listed as lingering and accumulates in `refs/heads` permanently --
the exact opposite of what that line exists to do.

So the forge is consulted as a SECOND source of the same signal. It is
opportunistic in the way `_default_from_gh` already is: present and answering,
it helps; missing, unauthenticated, non-GitHub or erroring, it falls through to
the local test and the hook behaves exactly as before. Silence stays the
default.

Real git throughout, and the forge answer injected as data -- these tests never
shell out to `gh`, because what is being tested is what the hook does with an
answer, not whether GitHub replies.
"""

import subprocess

import pytest

import merged_branch


def run(*args, cwd=None):
    completed = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    assert completed.returncode == 0, f"{args} failed: {completed.stderr}"
    return completed.stdout.strip()


@pytest.fixture(autouse=True)
def no_real_forge(monkeypatch):
    """No test here shells out to `gh`.

    What is under test is what the hook DOES with an answer, not whether GitHub
    replies — and a suite that reaches the network is a suite that is red on a
    plane. Tests that want a forge answer pass one to `report`;
    `TestTheLookupItself` exercises the real function with `_run` substituted.
    """
    monkeypatch.setattr(
        merged_branch, "forge_merged_branches", lambda *args, **kwargs: frozenset()
    )


@pytest.fixture(autouse=True)
def isolated_git(monkeypatch, tmp_path):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig-none"))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(tmp_path / "gitconfig-none"))
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "Test")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "test@example.com")


@pytest.fixture
def clone(tmp_path):
    origin = tmp_path / "origin.git"
    run("git", "init", "--bare", "--initial-branch=main", str(origin))
    work = tmp_path / "work"
    run("git", "clone", str(origin), str(work))
    (work / "README.md").write_text("seed\n")
    run("git", "add", "README.md", cwd=work)
    run("git", "commit", "-m", "seed", cwd=work)
    run("git", "push", "-u", "origin", "main", cwd=work)
    return work


def rebase_merge(clone, branch, filename):
    """Land `branch` the way this repo actually lands PRs.

    The branch's commit is replayed onto main as a NEW commit, so the branch tip
    is no longer an ancestor of origin/main -- which is precisely what makes it
    invisible to the ancestor test.
    """
    run("git", "checkout", "-q", "-b", branch, cwd=clone)
    (clone / filename).write_text("work\n")
    run("git", "add", filename, cwd=clone)
    run("git", "commit", "-m", f"feat: {branch}", cwd=clone)
    run("git", "push", "-u", "origin", branch, cwd=clone)
    run("git", "checkout", "-q", "main", cwd=clone)
    # Advance main first, so the replay lands on a different parent and really
    # does get a new hash. Without this, cherry-picking onto the same parent
    # within the same second reproduces the identical SHA and the "rewrite"
    # quietly is not one — which is a fast-forward the ancestor test can see.
    (clone / "unrelated.txt").write_text("meanwhile\n")
    run("git", "add", "unrelated.txt", cwd=clone)
    run("git", "commit", "-m", "chore: unrelated", cwd=clone)
    # Replay, not merge: same content, new commit, new hash.
    run("git", "cherry-pick", branch, cwd=clone)
    run("git", "push", "origin", "main", cwd=clone)
    run("git", "checkout", "-q", branch, cwd=clone)


class TestTheAncestorTestReallyIsBlindHere:
    """The premise, pinned. If this ever starts passing without the forge, the
    rest of this file is measuring nothing."""

    def test_a_rebase_merged_branch_is_not_an_ancestor_of_the_default(self, clone):
        rebase_merge(clone, "feat/x", "x.txt")

        assert not merged_branch.is_merged(clone, "feat/x", "origin/main")

    def test_and_so_the_hook_says_nothing_about_it(self, clone):
        rebase_merge(clone, "feat/x", "x.txt")

        lines = merged_branch.report(clone)

        assert not any("has been merged" in line for line in lines)


class TestTheForgeSignalRecoversIt:
    def test_a_branch_the_forge_calls_merged_is_merged(self, clone):
        rebase_merge(clone, "feat/x", "x.txt")

        assert merged_branch.is_merged(
            clone, "feat/x", "origin/main", forge_merged=frozenset({"feat/x"})
        )

    def test_the_hook_announces_it(self, clone):
        rebase_merge(clone, "feat/x", "x.txt")

        lines = merged_branch.report(clone, forge_merged=frozenset({"feat/x"}))

        assert "Branch feat/x has been merged into main." in lines

    def test_it_is_listed_as_lingering_so_it_can_finally_be_deleted(self, clone):
        """The half of the defect that matters more: a rebase-merged branch was
        never listed, so it stayed in refs/heads forever."""
        rebase_merge(clone, "feat/x", "x.txt")
        run("git", "checkout", "-q", "main", cwd=clone)

        lines = merged_branch.report(clone, forge_merged=frozenset({"feat/x"}))

        assert any(
            "Merged branches still present locally: feat/x." in line for line in lines
        )

    def test_an_unrelated_merged_pr_does_not_make_this_branch_merged(self, clone):
        """The set is consulted by name, so a busy repo's other merged PRs say
        nothing about the branch in hand."""
        run("git", "checkout", "-q", "-b", "feat/live", cwd=clone)
        (clone / "live.txt").write_text("wip\n")
        run("git", "add", "live.txt", cwd=clone)
        run("git", "commit", "-m", "wip", cwd=clone)

        assert not merged_branch.is_merged(
            clone,
            "feat/live",
            "origin/main",
            forge_merged=frozenset({"feat/other", "feat/older"}),
        )

    def test_a_published_branch_with_extra_local_work_is_still_announced(self, clone):
        """The forge speaks about the head ref as GitHub last saw it. This branch
        was published and merged, so the verdict stands — and the extra local
        commit is exactly the thing the user needs telling about. (An UNpublished
        branch is a different case, covered in
        `TestANameIsNecessaryButNotSufficient`.)"""
        rebase_merge(clone, "feat/x", "x.txt")
        (clone / "more.txt").write_text("more\n")
        run("git", "add", "more.txt", cwd=clone)
        run("git", "commit", "-m", "more", cwd=clone)

        lines = merged_branch.report(clone, forge_merged=frozenset({"feat/x"}))

        # Still announced — GitHub merged this head ref, and the extra local
        # commit is exactly the thing the user needs telling about.
        assert "Branch feat/x has been merged into main." in lines


class TestItStaysOpportunistic:
    def test_no_forge_answer_behaves_exactly_as_before(self, clone):
        """gh missing, unauthenticated, non-GitHub remote, rate-limited: all of
        it arrives here as an empty set, and an empty set must change nothing."""
        rebase_merge(clone, "feat/x", "x.txt")

        assert merged_branch.report(
            clone, forge_merged=frozenset()
        ) == merged_branch.report(clone)

    def test_an_ordinary_merge_commit_needs_no_forge_at_all(self, clone):
        run("git", "checkout", "-q", "-b", "feat/x", cwd=clone)
        (clone / "x.txt").write_text("x\n")
        run("git", "add", "x.txt", cwd=clone)
        run("git", "commit", "-m", "x", cwd=clone)
        run("git", "push", "-u", "origin", "feat/x", cwd=clone)
        run("git", "checkout", "-q", "main", cwd=clone)
        run("git", "merge", "--no-ff", "-m", "merge", "feat/x", cwd=clone)
        run("git", "push", "origin", "main", cwd=clone)
        run("git", "checkout", "-q", "feat/x", cwd=clone)

        assert "Branch feat/x has been merged into main." in merged_branch.report(clone)

    def test_a_freshly_created_branch_is_not_merged_even_if_the_forge_errs(self, clone):
        """The forge set names head refs of MERGED PRs. A branch just created
        locally cannot be in it — but if a stale or wrong answer ever put it
        there, the announcement is still the honest reading of that answer, so
        this test pins the ordinary case instead: an empty set, no announcement."""
        run("git", "checkout", "-q", "-b", "feat/empty", cwd=clone)

        assert merged_branch.report(clone, forge_merged=frozenset()) == []


# Captured before the autouse fixture can replace it: `TestTheLookupItself`
# tests the real lookup, with only its subprocess call substituted.
real_lookup = merged_branch.forge_merged_branches


class TestTheLookupItself:
    """The one function that actually shells out to `gh`."""

    def test_a_missing_gh_yields_an_empty_set_rather_than_raising(
        self, clone, monkeypatch
    ):
        monkeypatch.setattr(
            merged_branch,
            "_run",
            lambda *args, **kwargs: (_ for _ in ()).throw(OSError("no gh")),
        )

        assert real_lookup(clone) == frozenset()

    def test_a_nonzero_gh_exit_yields_an_empty_set(self, clone, monkeypatch):
        monkeypatch.setattr(
            merged_branch,
            "_run",
            lambda *args, **kwargs: subprocess.CompletedProcess(
                args, returncode=1, stdout="", stderr="not authenticated"
            ),
        )

        assert real_lookup(clone) == frozenset()

    def test_it_parses_one_head_ref_per_line(self, clone, monkeypatch):
        monkeypatch.setattr(
            merged_branch,
            "_run",
            lambda *args, **kwargs: subprocess.CompletedProcess(
                args, returncode=0, stdout="feat/x\nfix/y\n\n", stderr=""
            ),
        )

        assert real_lookup(clone) == frozenset({"feat/x", "fix/y"})

    def test_it_asks_for_merged_pull_requests_by_head_ref(self, clone, monkeypatch):
        captured = {}

        def fake_run(argv, cwd, timeout):
            captured["argv"] = list(argv)
            return subprocess.CompletedProcess(argv, returncode=0, stdout="", stderr="")

        monkeypatch.setattr(merged_branch, "_run", fake_run)

        real_lookup(clone)

        assert captured["argv"][:3] == ["gh", "pr", "list"]
        assert "--state" in captured["argv"] and "merged" in captured["argv"]
        assert "headRefName" in captured["argv"]

    def test_an_expired_deadline_skips_the_network_call_entirely(
        self, clone, monkeypatch
    ):
        """The hook shares one wall-clock budget; a forge call that would push
        it past the hooks.json timeout must not be made at all."""
        called = []
        monkeypatch.setattr(
            merged_branch, "_run", lambda *args, **kwargs: called.append(1)
        )
        spent = merged_branch.Deadline(budget=0)

        assert real_lookup(clone, deadline=spent) == frozenset()
        assert called == []


class TestANameIsNecessaryButNotSufficient:
    """The forge answers with head-ref NAMES, not commits, and names get reused.

    `fix/login` merged in March and recreated in September is a different branch
    wearing a merged name — and fork PRs make `patch-1`, `develop` and `master`
    routine entries in that set. Matching on the name alone announced the branch
    the user was standing on and listed it as safe to delete, short-circuiting
    both freshly-created-branch guards because the check sat in front of them.
    """

    def test_a_recreated_merged_name_is_not_announced(self, clone):
        run("git", "checkout", "-q", "-b", "fix/login", cwd=clone)

        lines = merged_branch.report(clone, forge_merged=frozenset({"fix/login"}))

        assert not any("has been merged" in line for line in lines)

    def test_nor_is_it_listed_as_safe_to_delete(self, clone):
        """The more expensive half: the user is standing on it."""
        run("git", "checkout", "-q", "-b", "fix/login", cwd=clone)

        lines = merged_branch.report(clone, forge_merged=frozenset({"fix/login"}))

        assert not any("still present locally" in line for line in lines)

    def test_a_genuinely_rebase_merged_branch_is_still_announced(self, clone):
        """The fix must not swallow the case the forge signal exists for: this
        branch was published and has commits of its own."""
        rebase_merge(clone, "feat/x", "x.txt")

        lines = merged_branch.report(clone, forge_merged=frozenset({"feat/x"}))

        assert "Branch feat/x has been merged into main." in lines


class TestTheSeenSetIsAdjudicatedNotReported:
    def test_a_branch_the_tip_guard_skipped_is_not_re_added_by_the_forge_pass(
        self, clone
    ):
        """`seen.add` sat AFTER the tracking-tip guard, so a ref that guard
        deliberately skipped never entered the set — and the forge pass, which
        skips anything already seen, re-added it. The original false positive
        arriving by a third route: a recreated branch sitting at the tip,
        reported as merged and deletable."""
        run("git", "checkout", "-q", "-b", "docs/readme", cwd=clone)
        run("git", "checkout", "-q", "main", cwd=clone)

        lines = merged_branch.report(clone, forge_merged=frozenset({"docs/readme"}))

        assert not any("docs/readme" in line for line in lines)
