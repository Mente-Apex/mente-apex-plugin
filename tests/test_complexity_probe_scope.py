"""Scope resolution, including the two forms the spec adds: a bare invocation
meaning the uncommitted working tree, and a line range naming one function."""

from complexity_probe_scope import ScopeSelection, parse_range, resolve_scope


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
        selection = resolve_scope("full", repo_root="/repo", git_runner=StubGitRunner())
        assert isinstance(selection, ScopeSelection)
        assert selection.description
