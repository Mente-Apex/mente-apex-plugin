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
        _, created, _ = create_worktrees(branch_repo["path"], "feature", LENSES)

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
        _, created, _ = create_worktrees(branch_repo["path"], "feature", LENSES)

        for worktree in created.values():
            assert (worktree / "feature.py").is_file()

    def test_one_worktree_per_lens_named_for_it(self, branch_repo):
        _, created, _ = create_worktrees(branch_repo["path"], "feature", LENSES)

        assert set(created) == set(LENSES)
        assert all(path.name == name for name, path in created.items())

    def test_they_are_detached_so_six_lenses_can_share_one_branch(self, branch_repo):
        """Not a preference: git refuses to check out one branch in two
        worktrees, so without --detach the second lens fails outright."""
        _, created, _ = create_worktrees(branch_repo["path"], "feature", LENSES)

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
        root, _, _ = create_worktrees(branch_repo["path"], "feature", LENSES)

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
        _, created, _ = create_worktrees(branch_repo["path"], "feature", LENSES)

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


class TestPathsAreResolvedNotAssumed:
    """A relative `--repo-root` used to fail 100% of the time, and fail with this
    module's own #156 alarm about a defect that had not occurred: `git worktree
    add` resolves a relative destination against `git -C <repo_root>`, while
    `_head_of` ran `git -C <destination>` against the PROCESS cwd."""

    def test_a_relative_repo_root_still_creates_a_verified_set(
        self, branch_repo, monkeypatch, tmp_path
    ):
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)
        relative_repo = Path("..") / branch_repo["path"].relative_to(tmp_path)

        root, created, commit = create_worktrees(relative_repo, "feature", LENSES)

        assert commit == branch_repo["branch_head"]
        for worktree in created.values():
            assert (worktree / "feature.py").is_file()
        assert root.is_absolute()

    def test_the_returned_paths_are_absolute_so_remove_works_from_anywhere(
        self, branch_repo
    ):
        """The payload hands `root` back for the teardown call, possibly from a
        different cwd."""
        root, created, _ = create_worktrees(branch_repo["path"], "feature", LENSES)

        assert root.is_absolute()
        assert all(path.is_absolute() for path in created.values())

    def test_the_verified_commit_is_the_one_reported(self, branch_repo):
        """Resolving the ref a second time for the payload could report a SHA
        other than the one the worktrees were checked against."""
        _, _, commit = create_worktrees(branch_repo["path"], "feature", LENSES)

        assert commit == branch_repo["branch_head"]


class TestAMissingGitIsReportedNotRaised:
    def test_an_oserror_becomes_a_stated_error_with_json_on_stdout(
        self, branch_repo, monkeypatch
    ):
        """Only TimeoutExpired was converted, so an OSError escaped `main` -- which
        catches only WorktreeSetupError -- as a traceback with NO json. The
        orchestrator parsed empty stdout, got no {"error": ...}, and the audit
        proceeded with no worktrees: the invisible failure this module refuses."""
        import lens_worktrees

        def no_git(*args, **kwargs):
            raise FileNotFoundError(2, "No such file or directory", "git")

        monkeypatch.setattr(lens_worktrees.subprocess, "run", no_git)

        with pytest.raises(WorktreeSetupError) as raised:
            create_worktrees(branch_repo["path"], "feature", LENSES)

        assert "could not run git" in str(raised.value)

    def test_the_cli_prints_that_error_as_json(self, branch_repo, monkeypatch, capsys):
        import lens_worktrees

        monkeypatch.setattr(
            lens_worktrees.subprocess,
            "run",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                FileNotFoundError(2, "No such file or directory", "git")
            ),
        )

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

        assert code == 2
        assert "could not run git" in json.loads(capsys.readouterr().out)["error"]
