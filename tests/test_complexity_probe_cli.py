"""The CLI wires the parts together. Exit code 1 is reserved for a blocking
gate verdict — never for a high number."""

import json

import complexity_probe


class TestOutputModes:
    def test_default_output_is_human_readable(self, tmp_path, capsys):
        source_file = tmp_path / "sample.py"
        source_file.write_text("def add(first, second):\n    return first + second\n")
        exit_code = complexity_probe.main([str(source_file)])
        captured = capsys.readouterr()
        assert exit_code == 0
        assert "add" in captured.out

    def test_json_output_parses(self, tmp_path, capsys):
        source_file = tmp_path / "sample.py"
        source_file.write_text("def add(first, second):\n    return first + second\n")
        complexity_probe.main([str(source_file), "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["status"] == "ran"


class TestExitCodes:
    def test_a_high_complexity_function_still_exits_zero(self, tmp_path, capsys):
        """Numbers never fail the run — only silence does."""
        branches = "\n".join(
            f"    if value == {index}:\n        return {index}" for index in range(25)
        )
        source_file = tmp_path / "branchy.py"
        source_file.write_text(f"def classify(value):\n{branches}\n    return -1\n")
        assert complexity_probe.main([str(source_file)]) == 0

    def test_gate_mode_on_a_successful_measurement_exits_zero(self, tmp_path):
        source_file = tmp_path / "sample.py"
        source_file.write_text("def add(first, second):\n    return first + second\n")
        assert complexity_probe.main([str(source_file), "--gate"]) == 0


class TestScopeWiring:
    def test_scope_full_is_accepted(self, tmp_path, capsys):
        (tmp_path / "sample.py").write_text("def add(a_value):\n    return a_value\n")
        exit_code = complexity_probe.main(
            ["--scope", "full", "--repo-root", str(tmp_path)]
        )
        assert exit_code == 0

    def test_an_empty_working_tree_exits_zero_and_says_so(self, tmp_path, capsys):
        """`tmp_path` is not a git repository, so scope resolution now fails
        loudly (task 4's fix to the old swallow-and-return-nothing behavior).
        The CLI must turn that failure into an `unverified` measurement rather
        than let the exception escape — a scope failure is exactly the kind of
        absence spec §2.3 requires to be reported as data, with a reason."""
        exit_code = complexity_probe.main(
            ["--scope", "working-tree", "--repo-root", str(tmp_path)]
        )
        captured = capsys.readouterr()
        assert exit_code == 0
        assert "unverified" in captured.out
        assert "scope could not be resolved" in captured.out

    def test_multiple_positional_paths_do_not_touch_git(self, tmp_path, capsys):
        """Two or more positional paths are taken literally and routed
        straight to the probe. `tmp_path` is not a git repository; if the CLI
        still queried git on the side (its return value went unused even
        before scope resolution could raise), this would now misreport a
        perfectly measurable pair of files as unverified.

        `--repo-root` must point at `tmp_path` here: without it,
        `arguments.repo_root` defaults to `"."`, the pytest process's real
        working directory — this project's own git repo — where the discarded
        `resolve_scope(None, repo_root=".")` call would succeed instead of
        raising, and the test would pass whether or not the fix is present."""
        first_file = tmp_path / "first.py"
        first_file.write_text("def add(first, second):\n    return first + second\n")
        second_file = tmp_path / "second.py"
        second_file.write_text("def sub(first, second):\n    return first - second\n")

        exit_code = complexity_probe.main(
            [str(first_file), str(second_file), "--repo-root", str(tmp_path)]
        )
        captured = capsys.readouterr()

        assert exit_code == 0
        assert "add" in captured.out
        assert "sub" in captured.out
        assert "unverified" not in captured.out
