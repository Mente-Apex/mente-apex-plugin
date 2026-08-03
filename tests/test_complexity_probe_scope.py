"""Scope resolution, including the two forms the spec adds: a bare invocation
meaning the uncommitted working tree, and a line range naming one function."""

import pytest

from complexity_probe_scope import GitRunner, ScopeSelection, parse_range, resolve_scope


class StubGitRunner:
    def __init__(self, changed_files=("src/OrderService.java",)):
        self.changed_files = list(changed_files)
        self.calls = []

    def changed_paths(self, mode):
        self.calls.append(mode)
        return list(self.changed_files)


class TestParsingARange:
    def test_a_range_is_split_into_path_and_bounds(self):
        assert parse_range("OrderService.java:40-120") == (
            "OrderService.java",
            40,
            120,
        )

    def test_a_bare_path_is_not_a_range(self):
        assert parse_range("src/orders/") is None

    def test_a_windows_style_drive_letter_is_not_a_range(self):
        assert parse_range("C:/src/OrderService.java") is None

    def test_a_reversed_range_is_rejected(self):
        assert parse_range("OrderService.java:120-40") is None


class TestResolvingScope:
    def test_no_argument_means_the_uncommitted_working_tree(self):
        git_runner = StubGitRunner()
        selection = resolve_scope(None, repo_root=".", git_runner=git_runner)
        assert git_runner.calls == ["working-tree"]
        assert selection.paths == ("src/OrderService.java",)

    def test_working_tree_is_the_same_as_no_argument(self):
        git_runner = StubGitRunner()
        selection = resolve_scope("working-tree", repo_root=".", git_runner=git_runner)
        assert selection.paths == ("src/OrderService.java",)

    def test_merge_base_asks_git_for_the_branch_diff(self):
        git_runner = StubGitRunner()
        resolve_scope("merge-base", repo_root=".", git_runner=git_runner)
        assert git_runner.calls == ["merge-base"]

    def test_full_is_the_repo_root_and_asks_git_nothing(self):
        git_runner = StubGitRunner()
        selection = resolve_scope("full", repo_root="/repo", git_runner=git_runner)
        assert selection.paths == ("/repo",)
        assert git_runner.calls == []

    def test_a_path_is_taken_literally(self):
        selection = resolve_scope(
            "src/orders/", repo_root=".", git_runner=StubGitRunner()
        )
        assert selection.paths == ("src/orders/",)
        assert selection.line_range is None

    def test_a_range_keeps_its_bounds(self):
        selection = resolve_scope(
            "OrderService.java:40-120", repo_root=".", git_runner=StubGitRunner()
        )
        assert selection.paths == ("OrderService.java",)
        assert selection.line_range == (40, 120)

    def test_an_empty_working_tree_yields_no_paths(self):
        selection = resolve_scope(
            None, repo_root=".", git_runner=StubGitRunner(changed_files=())
        )
        assert selection.paths == ()

    def test_every_selection_describes_itself_for_the_report(self):
        """Each form's description is the only thing that tells a reader what a
        measurement was taken against, so each is pinned by its words rather
        than by being merely non-empty."""
        described = {
            argument: resolve_scope(
                argument, repo_root="/repo", git_runner=StubGitRunner()
            )
            for argument in (None, "working-tree", "merge-base", "full", "src/orders")
        }
        assert all(
            isinstance(selection, ScopeSelection) for selection in described.values()
        )
        assert described[None].description == "uncommitted changes in the working tree"
        assert described["working-tree"].description == described[None].description
        assert described["merge-base"].description == "changes on this branch"
        assert described["full"].description == "the whole repository"
        assert described["src/orders"].description == "src/orders"

    def test_a_range_describes_its_bounds(self):
        selection = resolve_scope(
            "OrderService.java:40-120", repo_root=".", git_runner=StubGitRunner()
        )
        assert selection.description == "OrderService.java lines 40-120"


class StubFilesystem:
    def __init__(self, directories=()):
        self.directories = set(directories)

    def is_directory(self, path) -> bool:
        return path in self.directories


class TestARangeMustNameAFile:
    """Line numbers belong to one file. `<dir>:1-2` used to be honoured against
    every file under the tree at once — lines 1-2 of each, reported as a single
    measurement, which is a confident answer to a question nobody asked."""

    def test_a_range_on_a_directory_is_refused(self):
        with pytest.raises(ValueError, match="is a directory"):
            resolve_scope(
                "src/orders:1-2",
                repo_root=".",
                git_runner=StubGitRunner(),
                filesystem=StubFilesystem(directories=("src/orders",)),
            )

    def test_the_refusal_names_the_target(self):
        with pytest.raises(ValueError, match="src/orders"):
            resolve_scope(
                "src/orders:1-2",
                repo_root=".",
                git_runner=StubGitRunner(),
                filesystem=StubFilesystem(directories=("src/orders",)),
            )

    def test_a_range_on_a_file_is_untouched(self):
        selection = resolve_scope(
            "OrderService.java:40-120",
            repo_root=".",
            git_runner=StubGitRunner(),
            filesystem=StubFilesystem(directories=("src/orders",)),
        )
        assert selection.line_range == (40, 120)

    def test_the_same_directory_without_a_range_is_still_a_target(self):
        selection = resolve_scope(
            "src/orders",
            repo_root=".",
            git_runner=StubGitRunner(),
            filesystem=StubFilesystem(directories=("src/orders",)),
        )
        assert selection.paths == ("src/orders",)
        assert selection.line_range is None


class TestGitRunnerWithRealRepository:
    """Real-git tests verify GitRunner delegates correctly to mutation_gate_scope
    and both Criticals are fixed: untracked files are included, errors surface."""

    def test_working_tree_includes_an_untracked_file(self, git_repo_with_branch):
        repo_root, _ = git_repo_with_branch
        untracked_path = repo_root / "untracked_new_file.py"
        untracked_path.write_text("NEW_CODE = 1\n", encoding="utf-8")

        runner = GitRunner(str(repo_root))
        paths = runner.changed_paths("working-tree")

        assert "untracked_new_file.py" in paths

    def test_working_tree_includes_a_modified_tracked_file(self, git_repo_with_branch):
        repo_root, _ = git_repo_with_branch
        tracked_file = repo_root / "feature.py"
        tracked_file.write_text("FEATURE = 2\n", encoding="utf-8")

        runner = GitRunner(str(repo_root))
        paths = runner.changed_paths("working-tree")

        assert "feature.py" in paths

    def test_merge_base_finds_default_branch_without_remote(self, git_repo_with_branch):
        import subprocess

        repo_root, default_branch = git_repo_with_branch
        (repo_root / "feature_change.py").write_text("CHANGED = 1\n", encoding="utf-8")

        subprocess.run(
            ["git", "add", "."],
            cwd=repo_root,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-qm", "feature change"],
            cwd=repo_root,
            check=True,
            capture_output=True,
        )

        runner = GitRunner(str(repo_root))
        paths = runner.changed_paths("merge-base")

        assert "feature_change.py" in paths

    def test_merge_base_raises_when_default_branch_cannot_be_determined(self, tmp_path):
        import subprocess

        repo_root = tmp_path / "unusual_repo"
        repo_root.mkdir()

        subprocess.run(
            ["git", "init", "-b", "unusual-branch-name"],
            cwd=repo_root,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "t@example.com"],
            cwd=repo_root,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "T"],
            cwd=repo_root,
            check=True,
            capture_output=True,
        )

        (repo_root / "file.py").write_text("CODE = 1\n", encoding="utf-8")
        subprocess.run(
            ["git", "add", "."],
            cwd=repo_root,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-qm", "initial"],
            cwd=repo_root,
            check=True,
            capture_output=True,
        )

        runner = GitRunner(str(repo_root))
        with pytest.raises(ValueError, match="cannot determine the default branch"):
            runner.changed_paths("merge-base")
