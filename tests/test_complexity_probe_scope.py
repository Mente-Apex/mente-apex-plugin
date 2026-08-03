"""Scope resolution, including the two forms the spec adds: a bare invocation
meaning the uncommitted working tree, and a line range naming one function."""

import os

import pytest

from complexity_probe_scope import (
    GitRunner,
    LocalFilesystem,
    ScopeSelection,
    parse_range,
    resolve_literal_paths,
    resolve_scope,
)


class StubGitRunner:
    def __init__(self, changed_files=("src/OrderService.java",)):
        self.changed_files = list(changed_files)
        self.calls = []

    def changed_paths(self, mode):
        self.calls.append(mode)
        return list(self.changed_files)


class StubFilesystem:
    """A disk that answers about the fixture paths these tests name.

    `missing` rather than `present` because absence is the exception being
    tested: a test about something else states no paths at all and gets a disk
    where its fixtures are simply there, while every test that cares names the
    paths it wants gone.
    """

    def __init__(self, directories=(), missing=(), line_counts=None):
        self.directories = set(directories)
        self.missing = set(missing)
        self.line_counts = dict(line_counts or {})

    def is_directory(self, path) -> bool:
        return path in self.directories

    def exists(self, path) -> bool:
        return path not in self.missing

    def line_count(self, path) -> int | None:
        """`None` for a file nobody stated a length for — the same "I cannot
        tell" the real filesystem returns for a file it cannot read, which is
        never grounds for a refusal."""
        return self.line_counts.get(path)


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
        selection = resolve_scope(
            "full",
            repo_root="/repo",
            git_runner=git_runner,
            filesystem=StubFilesystem(),
        )
        assert selection.paths == ("/repo",)
        assert git_runner.calls == []

    def test_a_path_is_taken_literally(self):
        selection = resolve_scope(
            "src/orders/",
            repo_root=".",
            git_runner=StubGitRunner(),
            filesystem=StubFilesystem(),
        )
        assert selection.paths == ("src/orders/",)
        assert selection.line_range is None

    def test_a_range_keeps_its_bounds(self):
        selection = resolve_scope(
            "OrderService.java:40-120",
            repo_root=".",
            git_runner=StubGitRunner(),
            filesystem=StubFilesystem(),
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
                argument,
                repo_root="/repo",
                git_runner=StubGitRunner(),
                filesystem=StubFilesystem(),
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
            "OrderService.java:40-120",
            repo_root=".",
            git_runner=StubGitRunner(),
            filesystem=StubFilesystem(),
        )
        assert selection.description == "OrderService.java lines 40-120"


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


class TestATargetMustExist:
    """A path that is not there produced a confident, empty measurement:
    `nosuchfile.py:1-2` rendered "no functions touched" with status `ran`. A
    typo'd path in a review command read exactly like a clean file."""

    def test_a_missing_ranged_path_is_refused(self):
        with pytest.raises(ValueError, match="no such path"):
            resolve_scope(
                "nosuchfile.py:1-2",
                repo_root=".",
                git_runner=StubGitRunner(),
                filesystem=StubFilesystem(missing=("nosuchfile.py",)),
            )

    def test_a_missing_bare_path_is_refused(self):
        """The range is not the cause — the bare form was just as confident."""
        with pytest.raises(ValueError, match="no such path"):
            resolve_scope(
                "nosuchfile.py",
                repo_root=".",
                git_runner=StubGitRunner(),
                filesystem=StubFilesystem(missing=("nosuchfile.py",)),
            )

    def test_the_refusal_names_the_target(self):
        with pytest.raises(ValueError, match="nosuchfile.py"):
            resolve_scope(
                "nosuchfile.py",
                repo_root=".",
                git_runner=StubGitRunner(),
                filesystem=StubFilesystem(missing=("nosuchfile.py",)),
            )

    def test_a_missing_directory_range_still_says_it_is_a_directory(self):
        """Order matters: a directory that exists gets the answer that names
        its actual problem, not a bare "no such path"."""
        with pytest.raises(ValueError, match="is a directory"):
            resolve_scope(
                "src/orders:1-2",
                repo_root=".",
                git_runner=StubGitRunner(),
                filesystem=StubFilesystem(directories=("src/orders",)),
            )

    def test_a_path_that_is_there_is_untouched(self):
        selection = resolve_scope(
            "OrderService.java",
            repo_root=".",
            git_runner=StubGitRunner(),
            filesystem=StubFilesystem(missing=("somethingelse.py",)),
        )
        assert selection.paths == ("OrderService.java",)

    def test_a_deleted_file_in_a_git_diff_is_not_refused(self):
        """The case this guard must not break. A deleted file legitimately
        appears in a working-tree diff; refusing the whole run over an ordinary
        deletion would be a worse failure than the one being fixed."""
        selection = resolve_scope(
            "working-tree",
            repo_root=".",
            git_runner=StubGitRunner(changed_files=("src/Deleted.java",)),
            filesystem=StubFilesystem(missing=("src/Deleted.java",)),
        )
        assert selection.paths == ("src/Deleted.java",)

    def test_a_deleted_file_on_the_branch_is_not_refused_either(self):
        selection = resolve_scope(
            "merge-base",
            repo_root=".",
            git_runner=StubGitRunner(changed_files=("src/Deleted.java",)),
            filesystem=StubFilesystem(missing=("src/Deleted.java",)),
        )
        assert selection.paths == ("src/Deleted.java",)


class TestTheRepoRootMustExistToo:
    """The last caller-named path answered confidently. `--scope full
    --repo-root <typo>` reported `ran` with no functions — #137's defect one
    flag over, in the form README documents for feeding an audit — and the two
    git forms crashed with a `FileNotFoundError` carrying exit 1, the code
    reserved for a blocking gate verdict."""

    def test_full_against_a_missing_root_is_refused(self):
        with pytest.raises(ValueError, match="no such path"):
            resolve_scope(
                "full",
                repo_root="/definitely/not/here",
                git_runner=StubGitRunner(),
                filesystem=StubFilesystem(missing=("/definitely/not/here",)),
            )

    def test_the_working_tree_against_a_missing_root_is_refused(self):
        """Refused before git is asked, so the crash cannot happen."""
        git_runner = StubGitRunner()
        with pytest.raises(ValueError, match="no such path"):
            resolve_scope(
                None,
                repo_root="/definitely/not/here",
                git_runner=git_runner,
                filesystem=StubFilesystem(missing=("/definitely/not/here",)),
            )
        assert git_runner.calls == []

    def test_merge_base_against_a_missing_root_is_refused(self):
        with pytest.raises(ValueError, match="no such path"):
            resolve_scope(
                "merge-base",
                repo_root="/definitely/not/here",
                git_runner=StubGitRunner(),
                filesystem=StubFilesystem(missing=("/definitely/not/here",)),
            )

    def test_a_named_path_does_not_consult_the_repo_root(self):
        """The control. Only the three vocabulary words resolve *through* the
        root; a caller who names a file outright is not asking about it, and
        refusing on a root that form never reads would be a surprise."""
        selection = resolve_scope(
            "OrderService.java",
            repo_root="/definitely/not/here",
            git_runner=StubGitRunner(),
            filesystem=StubFilesystem(missing=("/definitely/not/here",)),
        )
        assert selection.paths == ("OrderService.java",)


class TestARangeMustNameLinesThatExist:
    """`real.py:9000-9001` on a four-line file reported `ran` with no
    functions: the path is there, the lines are not. The same confident answer
    about nothing, one input further along than a missing path."""

    def test_a_range_beginning_past_the_last_line_is_refused(self):
        with pytest.raises(ValueError, match="name nothing"):
            resolve_scope(
                "File.py:9000-9001",
                repo_root=".",
                git_runner=StubGitRunner(),
                filesystem=StubFilesystem(line_counts={"File.py": 4}),
            )

    def test_the_refusal_states_the_length_it_measured_against(self):
        with pytest.raises(ValueError, match="4 line"):
            resolve_scope(
                "File.py:9000-9001",
                repo_root=".",
                git_runner=StubGitRunner(),
                filesystem=StubFilesystem(line_counts={"File.py": 4}),
            )

    def test_a_range_merely_overhanging_the_end_is_kept(self):
        """ "From line 3 to the end" is an ordinary gesture and selects real
        lines. Refusing it would hide a target the caller pointed straight at
        — this guard's own failure, in the other direction."""
        selection = resolve_scope(
            "File.py:3-9000",
            repo_root=".",
            git_runner=StubGitRunner(),
            filesystem=StubFilesystem(line_counts={"File.py": 4}),
        )
        assert selection.line_range == (3, 9000)

    def test_a_range_ending_on_the_last_line_is_kept(self):
        selection = resolve_scope(
            "File.py:4-4",
            repo_root=".",
            git_runner=StubGitRunner(),
            filesystem=StubFilesystem(line_counts={"File.py": 4}),
        )
        assert selection.line_range == (4, 4)

    def test_a_file_whose_length_cannot_be_told_is_not_refused(self):
        """An unreadable file already reaches the user as `unverified` from
        the probe, with the read error named. Refusing here would replace a
        specific cause with a guess."""
        selection = resolve_scope(
            "File.py:9000-9001",
            repo_root=".",
            git_runner=StubGitRunner(),
            filesystem=StubFilesystem(),
        )
        assert selection.line_range == (9000, 9001)


class TestLiteralPathsMustExistToo:
    """Two or more positional paths never reach `resolve_scope`, so without
    their own check `probe.py real.py typo.py` kept reporting `ran` — the same
    defect one input over from the one being fixed."""

    def test_a_missing_path_among_several_is_refused(self):
        with pytest.raises(ValueError, match="no such path"):
            resolve_literal_paths(
                ("first.py", "typo.py"),
                filesystem=StubFilesystem(missing=("typo.py",)),
            )

    def test_only_the_missing_paths_are_named(self):
        with pytest.raises(ValueError) as refusal:
            resolve_literal_paths(
                ("first.py", "typo.py"),
                filesystem=StubFilesystem(missing=("typo.py",)),
            )
        assert "typo.py" in str(refusal.value)
        assert "first.py" not in str(refusal.value)

    def test_every_missing_path_is_named_not_just_the_first(self):
        with pytest.raises(ValueError) as refusal:
            resolve_literal_paths(
                ("one_typo.py", "another_typo.py"),
                filesystem=StubFilesystem(missing=("one_typo.py", "another_typo.py")),
            )
        assert "one_typo.py" in str(refusal.value)
        assert "another_typo.py" in str(refusal.value)

    def test_paths_that_are_all_there_pass_through_described(self):
        selection = resolve_literal_paths(
            ("first.py", "second.py"), filesystem=StubFilesystem()
        )
        assert selection.paths == ("first.py", "second.py")
        assert selection.line_range is None
        assert selection.description == "first.py, second.py"


class TestLocalFilesystemAgainstRealFiles:
    """The stub answers what these tests assert; this class is what keeps the
    stub honest about the collaborator it stands in for."""

    def test_it_counts_the_lines_of_a_real_file(self, tmp_path):
        source_file = tmp_path / "File.py"
        source_file.write_text("one\ntwo\nthree\n", encoding="utf-8")
        assert LocalFilesystem().line_count(str(source_file)) == 3

    def test_a_final_line_without_a_newline_still_counts(self, tmp_path):
        source_file = tmp_path / "File.py"
        source_file.write_text("one\ntwo", encoding="utf-8")
        assert LocalFilesystem().line_count(str(source_file)) == 2

    def test_an_empty_file_has_no_lines(self, tmp_path):
        source_file = tmp_path / "Empty.py"
        source_file.write_text("", encoding="utf-8")
        assert LocalFilesystem().line_count(str(source_file)) == 0

    def test_bytes_no_text_decoder_would_accept_still_count(self, tmp_path):
        """Read as bytes, so an encoding a text read would choke on is a line
        count like any other rather than a crash inside scope resolution."""
        source_file = tmp_path / "Odd.py"
        source_file.write_bytes(b"\xff\xfe binary-ish\n second\n")
        assert LocalFilesystem().line_count(str(source_file)) == 2

    def test_a_file_that_cannot_be_read_reports_no_count(self, tmp_path):
        if os.geteuid() == 0:
            pytest.skip("running as root: file mode 000 is still readable")
        source_file = tmp_path / "Locked.py"
        source_file.write_text("one\n", encoding="utf-8")
        source_file.chmod(0o000)
        try:
            assert LocalFilesystem().line_count(str(source_file)) is None
        finally:
            source_file.chmod(0o600)

    def test_a_missing_file_reports_no_count_rather_than_raising(self, tmp_path):
        assert LocalFilesystem().line_count(str(tmp_path / "gone.py")) is None


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
