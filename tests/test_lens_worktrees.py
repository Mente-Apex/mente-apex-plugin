"""Worktrees cut at the ref actually under review (issue #156).

The reported failure: the harness cut every agent's worktree at the branch's
merge-base, so the code under audit was absent from all six. `isolation:
"worktree"` takes no ref, so the plugin cannot direct it -- the orchestrator has
to make them itself. That is only an improvement if the ref is *verified*, which
is what most of these tests are about: a worktree at the wrong commit must be
refused here, not noticed three phases later by an agent reading absent files.

Real git throughout, no fakes. The bug being fixed is a fact about what git
actually did, and a fake `git worktree add` that returns 0 would have passed
happily while the real one cut at the wrong commit.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from lens_worktrees import (
    WorktreeSetupError,
    create_worktrees,
    main,
    remove_worktrees,
    resolve_ref,
)

LENSES = ("solid", "gof", "ddd")


def commit_file(repo, name, content, message):
    (repo / name).write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", message], check=True)
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


@pytest.fixture
def branch_repo(tmp_path):
    """A repo whose branch is ahead of main — the shape that broke.

    `main` has `base.py` only; the branch adds `feature.py`. A worktree cut at
    the merge-base therefore does NOT contain `feature.py`, which is exactly
    what five analyzers silently worked around.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "t@example.com"], check=True
    )
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "T"], check=True)
    merge_base = commit_file(repo, "base.py", "BASE = 1\n", "base")
    subprocess.run(
        ["git", "-C", str(repo), "checkout", "-q", "-b", "feature"], check=True
    )
    branch_head = commit_file(repo, "feature.py", "FEATURE = 1\n", "feature")
    return {"path": repo, "merge_base": merge_base, "branch_head": branch_head}


class TestTheWorktreeCarriesTheCodeUnderReview:
    def test_every_lens_gets_the_branch_commit_not_the_merge_base(self, branch_repo):
        """The headline defect, stated as a test: six worktrees at the branch."""
        _, created = create_worktrees(branch_repo["path"], "feature", LENSES)

        for worktree in created.values():
            head = subprocess.run(
                ["git", "-C", str(worktree), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            assert head == branch_repo["branch_head"]
            assert head != branch_repo["merge_base"]

    def test_the_file_the_audit_is_about_is_actually_there(self, branch_repo):
        """The ref is a proxy; this is the thing that matters. In the reported
        run the sources under review simply did not exist in any worktree."""
        _, created = create_worktrees(branch_repo["path"], "feature", LENSES)

        for worktree in created.values():
            assert (worktree / "feature.py").is_file()

    def test_one_worktree_per_lens_named_for_it(self, branch_repo):
        _, created = create_worktrees(branch_repo["path"], "feature", LENSES)

        assert set(created) == set(LENSES)
        assert all(path.name == name for name, path in created.items())

    def test_they_are_detached_so_six_lenses_can_share_one_branch(self, branch_repo):
        """Not a preference: git refuses to check out one branch in two
        worktrees, so without --detach the second lens fails outright."""
        _, created = create_worktrees(branch_repo["path"], "feature", LENSES)

        for worktree in created.values():
            status = subprocess.run(
                ["git", "-C", str(worktree), "status", "-sb"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            assert "HEAD (no branch)" in status or "detached" in status

    def test_the_set_lives_outside_the_repository(self, branch_repo):
        """A worktree nested inside the tree it was cut from is a tree that
        contains itself, and every file walk downstream doubles."""
        root, _ = create_worktrees(branch_repo["path"], "feature", LENSES)

        assert branch_repo["path"] not in root.parents and root != branch_repo["path"]


class TestARefThatCannotBeHonouredIsRefused:
    def test_an_unknown_ref_fails_before_anything_is_created(self, branch_repo):
        with pytest.raises(WorktreeSetupError) as raised:
            create_worktrees(branch_repo["path"], "no-such-branch", LENSES)

        assert "cannot resolve" in str(raised.value)
        registered = subprocess.run(
            ["git", "-C", str(branch_repo["path"]), "worktree", "list"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert registered.count("\n") == 1  # the main checkout only

    def test_a_worktree_landing_at_the_wrong_commit_tears_the_set_down(
        self, branch_repo, monkeypatch
    ):
        """The verification, exercised. `git worktree add` can report success
        and leave a checkout at another commit -- a ref that moved mid-run, a
        hook rewriting HEAD -- and that failure is invisible to the agent handed
        the path. Here the HEAD read is forced to disagree."""
        import lens_worktrees

        real_run_git = lens_worktrees._run_git

        def lying_run_git(repo_root, *arguments):
            if arguments[:2] == ("rev-parse", "HEAD"):
                return subprocess.CompletedProcess(
                    arguments, returncode=0, stdout="0" * 40 + "\n", stderr=""
                )
            return real_run_git(repo_root, *arguments)

        with pytest.raises(WorktreeSetupError) as raised:
            create_worktrees(
                branch_repo["path"], "feature", LENSES, run_git=lying_run_git
            )

        assert "not the requested" in str(raised.value)
        registered = subprocess.run(
            ["git", "-C", str(branch_repo["path"]), "worktree", "list"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert registered.count("\n") == 1

    def test_a_partial_set_is_never_handed_over(self, branch_repo, tmp_path):
        """Some lenses auditing the branch and some auditing whatever their
        fallback found is the silent-mixed-evidence case the consolidated
        report cannot detect."""
        root = tmp_path / "set"
        root.mkdir()
        # A plain file where the third worktree must go: git cannot create it.
        (root / "ddd").write_text("in the way\n", encoding="utf-8")

        with pytest.raises(WorktreeSetupError):
            create_worktrees(branch_repo["path"], "feature", LENSES, root=root)

        registered = subprocess.run(
            ["git", "-C", str(branch_repo["path"]), "worktree", "list"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert registered.count("\n") == 1


class TestResolveRef:
    def test_it_returns_a_full_sha_not_the_name(self, branch_repo):
        """Compared against the name, a worktree cut at a different commit the
        ref later moved to would verify clean."""
        assert resolve_ref(branch_repo["path"], "feature") == branch_repo["branch_head"]

    def test_head_resolves_to_the_checked_out_commit(self, branch_repo):
        assert resolve_ref(branch_repo["path"], "HEAD") == branch_repo["branch_head"]


class TestTeardown:
    def test_removal_unregisters_every_worktree(self, branch_repo):
        _, created = create_worktrees(branch_repo["path"], "feature", LENSES)

        failures = remove_worktrees(branch_repo["path"], created.values())

        assert failures == []
        registered = subprocess.run(
            ["git", "-C", str(branch_repo["path"]), "worktree", "list"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert registered.count("\n") == 1

    def test_it_reports_failures_rather_than_raising(self, branch_repo, tmp_path):
        """Teardown runs after the audit's results exist, so it must never
        replace them with an exception -- the same rule the mutation gate's
        workspace teardown follows."""
        failures = remove_worktrees(branch_repo["path"], [tmp_path / "never-existed"])

        assert len(failures) == 1
        assert "never-existed" in failures[0][0]


class TestTheCli:
    @staticmethod
    def run_cli(*arguments):
        completed = subprocess.run(
            [
                sys.executable,
                str(
                    Path(__file__).resolve().parents[1]
                    / "scripts"
                    / "lens_worktrees.py"
                ),
                *arguments,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        return completed, json.loads(completed.stdout)

    def test_create_prints_the_paths_an_orchestrator_hands_to_each_brief(
        self, branch_repo
    ):
        completed, payload = self.run_cli(
            "create",
            "--repo-root",
            str(branch_repo["path"]),
            "--ref",
            "feature",
            "--lenses",
            *LENSES,
        )

        assert completed.returncode == 0
        assert set(payload["worktrees"]) == set(LENSES)
        assert payload["commit"] == branch_repo["branch_head"]

    def test_create_reports_a_bad_ref_as_an_error_not_a_traceback(self, branch_repo):
        completed, payload = self.run_cli(
            "create",
            "--repo-root",
            str(branch_repo["path"]),
            "--ref",
            "nope",
            "--lenses",
            *LENSES,
        )

        assert completed.returncode == 2
        assert "cannot resolve" in payload["error"]
        assert "Traceback" not in completed.stderr

    def test_remove_cleans_up_the_set_it_was_given(self, branch_repo):
        _, created = self.run_cli(
            "create",
            "--repo-root",
            str(branch_repo["path"]),
            "--ref",
            "feature",
            "--lenses",
            *LENSES,
        )
        root = created["root"]

        completed, payload = self.run_cli(
            "remove",
            "--repo-root",
            str(branch_repo["path"]),
            "--root",
            root,
            "--lenses",
            *LENSES,
        )

        assert completed.returncode == 0
        assert payload["failures"] == []

    def test_main_is_importable_and_returns_an_exit_code(self, branch_repo, capsys):
        code = main(
            [
                "create",
                "--repo-root",
                str(branch_repo["path"]),
                "--ref",
                "feature",
                "--lenses",
                *LENSES,
            ]
        )

        assert code == 0
        assert json.loads(capsys.readouterr().out)["ref"] == "feature"
