"""The CLI wires the parts together. Exit code 1 is reserved for a blocking
gate verdict — never for a high number."""

import json
import os

import pytest

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


class TestGateReporting:
    def test_gate_flag_adds_verdict_to_output(self, tmp_path, capsys):
        """When --gate is passed, the verdict is printed to stdout.
        The verdict is separate from the measurement and should appear in output."""
        source_file = tmp_path / "sample.py"
        source_file.write_text("def add(first, second):\n    return first + second\n")

        # Measure without --gate
        exit_code_no_gate = complexity_probe.main([str(source_file)])
        output_no_gate = capsys.readouterr().out
        assert exit_code_no_gate == 0

        # Measure with --gate
        exit_code_with_gate = complexity_probe.main([str(source_file), "--gate"])
        output_with_gate = capsys.readouterr().out
        assert exit_code_with_gate == 0

        # The outputs should differ: --gate adds the verdict
        assert output_no_gate != output_with_gate
        assert output_with_gate.startswith(output_no_gate)  # Gate output is a superset
        assert "measured" in output_with_gate  # The verdict is added

    def test_gate_verdict_appears_for_successful_measurement(self, tmp_path, capsys):
        """The gate verdict should report how many functions were measured."""
        source_file = tmp_path / "functions.py"
        source_file.write_text("def first():\n    pass\n\ndef second():\n    pass\n")
        complexity_probe.main([str(source_file), "--gate"])
        captured = capsys.readouterr().out
        # The verdict should report the count
        assert "measured 2 function(s)" in captured

    def test_gate_json_mode_produces_valid_json_with_verdict_field(
        self, tmp_path, capsys
    ):
        """With --json --gate, the entire stdout is a single valid JSON document
        that includes the verdict as a field in the payload."""
        source_file = tmp_path / "sample.py"
        source_file.write_text("def add(first, second):\n    return first + second\n")
        exit_code = complexity_probe.main([str(source_file), "--json", "--gate"])
        assert exit_code == 0

        captured = capsys.readouterr().out

        # The entire output should parse as one valid JSON document.
        # No prefix-scanning, no special handling — it should all be JSON.
        json_payload = json.loads(captured)
        assert "status" in json_payload, "Payload missing status field"
        assert "verdict" in json_payload, "Payload missing verdict field (--gate)"
        assert "status" in json_payload["verdict"], "Verdict missing status"
        assert "message" in json_payload["verdict"], "Verdict missing message"


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


class TestABadConfigFileNeverCrashesTheRun:
    """Exit 1 is this branch's reserved code for a blocking gate verdict, and
    the whole "`--gate` is a reporter, not a blocker" ruling rests on it being
    unreachable. It was reachable by crash: a typo in someone else's config
    file produced a traceback and exit 1. Each shape below did so before the
    fix; each must now produce a measurement and a stated limit of none."""

    def _sample(self, tmp_path):
        source_file = tmp_path / "sample.py"
        source_file.write_text("def add(first, second):\n    return first + second\n")
        return source_file

    def test_a_non_integer_ruff_limit_still_measures(self, tmp_path, capsys):
        """`ValueError: invalid literal for int() with base 10: 'ten'`."""
        (tmp_path / "pyproject.toml").write_text(
            '[tool.ruff.lint.mccabe]\nmax-complexity = "ten"\n'
        )
        exit_code = complexity_probe.main(
            [str(self._sample(tmp_path)), "--repo-root", str(tmp_path), "--json"]
        )
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert exit_code == 0
        assert payload["status"] == "ran"
        assert payload["thresholds"]["cyclomatic_complexity"] is None
        # …and the typo is named rather than reported as "this repo declares
        # no limit", which is what a repo with no config at all gets.
        assert payload["thresholds"]["source"] != "none declared"
        assert payload["thresholds"]["diagnostics"]
        assert "ten" in captured.err

    def test_an_unreadable_pyproject_still_measures(self, tmp_path, capsys):
        """`PermissionError`, which no ruff-source guard caught."""
        if os.geteuid() == 0:
            pytest.skip("running as root: file mode 000 is still readable")
        config_path = tmp_path / "pyproject.toml"
        config_path.write_text("[tool.ruff.lint.mccabe]\nmax-complexity = 8\n")
        config_path.chmod(0o000)
        try:
            exit_code = complexity_probe.main(
                [str(self._sample(tmp_path)), "--repo-root", str(tmp_path)]
            )
        finally:
            config_path.chmod(0o600)
        captured = capsys.readouterr()
        assert exit_code == 0
        assert "add" in captured.out
        # The human sinks never render the threshold source, so a config the
        # repo declared but nobody could open is announced on stderr.
        assert "pyproject.toml" in captured.err

    def test_an_eslintrc_whose_root_is_a_list_still_measures(self, tmp_path, capsys):
        """`AttributeError: 'list' object has no attribute 'get'`."""
        (tmp_path / ".eslintrc.json").write_text("[1,2,3]\n")
        exit_code = complexity_probe.main(
            [str(self._sample(tmp_path)), "--repo-root", str(tmp_path)]
        )
        captured = capsys.readouterr()
        assert exit_code == 0
        assert "add" in captured.out
        assert ".eslintrc.json" in captured.err

    def test_the_cause_survives_another_source_declaring_a_limit(
        self, tmp_path, capsys
    ):
        """The run that looks healthiest is the one where the cause used to
        vanish: `source` names the *winning* config, so printing it said
        nothing about the typo in the config that lost."""
        (tmp_path / ".eslintrc.json").write_text(
            '{"rules": {"complexity": ["error", 9]}}'
        )
        (tmp_path / "pyproject.toml").write_text(
            '[tool.ruff.lint.mccabe]\nmax-complexity = "ten"\n'
        )
        complexity_probe.main(
            [str(self._sample(tmp_path)), "--repo-root", str(tmp_path), "--json"]
        )
        captured = capsys.readouterr()
        assert json.loads(captured.out)["thresholds"]["cyclomatic_complexity"] == 9
        assert "ten" in captured.err

    def test_a_repo_declaring_nothing_says_nothing_on_stderr(self, tmp_path, capsys):
        """The control: declaring no limit is an ordinary repo, not a fault,
        and must stay quiet."""
        complexity_probe.main(
            [str(self._sample(tmp_path)), "--repo-root", str(tmp_path)]
        )
        assert capsys.readouterr().err == ""

    def test_a_source_that_raises_anyway_degrades_and_says_why(
        self, tmp_path, capsys, monkeypatch
    ):
        """The backstop. Each source guards its own reads, but that is a
        convention every future source has to remember; this makes the
        invariant structural. The cause must reach the user rather than be
        swallowed into a bare "none declared"."""

        def exploding_discovery(repo_root, sources=None):
            raise RuntimeError("a source nobody guarded")

        monkeypatch.setattr(
            complexity_probe, "discover_thresholds", exploding_discovery
        )
        exit_code = complexity_probe.main(
            [str(self._sample(tmp_path)), "--repo-root", str(tmp_path), "--json"]
        )
        captured = capsys.readouterr()
        payload = json.loads(captured.out)

        assert exit_code == 0
        assert payload["status"] == "ran"
        assert payload["thresholds"]["cyclomatic_complexity"] is None
        assert "a source nobody guarded" in payload["thresholds"]["source"]
        # The two human sinks never render the threshold source, so the cause
        # is announced on stderr too — where it cannot corrupt the JSON.
        assert "a source nobody guarded" in captured.err


class TestALineRangeNarrowsWhatIsReported:
    """`File.py:1-2` used to report every function in File.py: the range was
    parsed, echoed in the scope description, and then discarded. That is a
    confident number attributed to the wrong target — the failure this probe
    exists to avoid. Three shipped surfaces advertise the range form."""

    TWO_FUNCTIONS = (
        "def tiny(value):\n"
        "    return value\n"
        "\n"
        "\n"
        "def big(value):\n"
        "    if value == 1:\n"
        "        return 1\n"
        "    if value == 2:\n"
        "        return 2\n"
        "    if value == 3:\n"
        "        return 3\n"
        "    return 0\n"
    )

    def _measured_names(self, capsys):
        return capsys.readouterr().out

    def test_a_range_covering_one_of_two_reports_only_that_one(self, tmp_path, capsys):
        source_file = tmp_path / "File.py"
        source_file.write_text(self.TWO_FUNCTIONS)
        exit_code = complexity_probe.main([f"{source_file}:1-2"])
        output = self._measured_names(capsys)
        assert exit_code == 0
        assert "tiny" in output
        assert "big" not in output

    def test_a_range_covering_the_other_reports_only_the_other(self, tmp_path, capsys):
        source_file = tmp_path / "File.py"
        source_file.write_text(self.TWO_FUNCTIONS)
        complexity_probe.main([f"{source_file}:5-12"])
        output = self._measured_names(capsys)
        assert "big" in output
        assert "tiny" not in output

    def test_a_range_covering_neither_reports_none(self, tmp_path, capsys):
        """Lines 3-4 are the blank lines between the two functions."""
        source_file = tmp_path / "File.py"
        source_file.write_text(self.TWO_FUNCTIONS)
        exit_code = complexity_probe.main([f"{source_file}:3-4"])
        output = self._measured_names(capsys)
        assert exit_code == 0
        assert "no functions touched" in output
        assert "tiny" not in output
        assert "big" not in output

    def test_a_function_straddling_the_boundary_is_kept(self, tmp_path, capsys):
        """Overlap, not containment. `big` spans lines 5-12 and the request
        stops at line 6, so `big` is only partly inside it — but it is the
        function the request is pointing at, and dropping it would hide the
        target while still reporting confidently."""
        source_file = tmp_path / "File.py"
        source_file.write_text(self.TWO_FUNCTIONS)
        complexity_probe.main([f"{source_file}:6-6"])
        output = self._measured_names(capsys)
        assert "big" in output
        assert "tiny" not in output

    def test_the_whole_file_still_reports_both(self, tmp_path, capsys):
        """The control: narrowing only happens when a range was asked for."""
        source_file = tmp_path / "File.py"
        source_file.write_text(self.TWO_FUNCTIONS)
        complexity_probe.main([str(source_file)])
        output = self._measured_names(capsys)
        assert "tiny" in output
        assert "big" in output

    def test_the_gate_verdict_counts_only_the_narrowed_functions(
        self, tmp_path, capsys
    ):
        """Narrowing happens before the verdict is evaluated, so the two
        cannot disagree about how much was measured."""
        source_file = tmp_path / "File.py"
        source_file.write_text(self.TWO_FUNCTIONS)
        complexity_probe.main([f"{source_file}:1-2", "--gate"])
        assert "measured 1 function(s)" in capsys.readouterr().out


class TestWhatWasMeasuredIsStated:
    """ "No functions" is two different facts. A file with nothing in it and a
    range that selected nothing rendered byte-identically — text and JSON both
    — so a user could not tell "there is nothing here" from "I scoped to lines
    that hold nothing". The selection has always described itself; nobody read
    it."""

    def test_a_range_that_selects_nothing_still_says_what_was_asked_for(
        self, tmp_path, capsys
    ):
        source_file = tmp_path / "File.py"
        source_file.write_text("def tiny(value):\n    return value\n\n\n")
        complexity_probe.main([f"{source_file}:3-4"])
        output = capsys.readouterr().out
        assert "no functions touched" in output
        assert "lines 3-4" in output

    def test_an_empty_file_and_an_empty_range_no_longer_read_alike(
        self, tmp_path, capsys
    ):
        source_file = tmp_path / "File.py"
        source_file.write_text("def tiny(value):\n    return value\n\n\n")
        empty_file = tmp_path / "Empty.py"
        empty_file.write_text("CONSTANT = 1\n")

        complexity_probe.main([f"{source_file}:3-4"])
        ranged_output = capsys.readouterr().out
        complexity_probe.main([str(empty_file)])
        empty_output = capsys.readouterr().out

        assert "no functions" in ranged_output
        assert "no functions" in empty_output
        assert ranged_output != empty_output

    def test_the_artifact_payload_carries_the_scope(self, tmp_path, capsys):
        source_file = tmp_path / "File.py"
        source_file.write_text("def tiny(value):\n    return value\n\n\n")
        complexity_probe.main([f"{source_file}:3-4", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["functions"] == []
        assert "lines 3-4" in payload["scope"]

    def test_the_whole_repository_names_itself_too(self, tmp_path, capsys):
        """Every scope form describes itself, not just the range."""
        (tmp_path / "sample.py").write_text("def add(value):\n    return value\n")
        complexity_probe.main(["--scope", "full", "--repo-root", str(tmp_path)])
        assert "the whole repository" in capsys.readouterr().out

    def test_several_literal_paths_name_all_of_them(self, tmp_path, capsys):
        """Two or more positional paths never reach `resolve_scope`, so this is
        the one description the CLI mints itself."""
        first_file = tmp_path / "first.py"
        first_file.write_text("def add(one, two):\n    return one + two\n")
        second_file = tmp_path / "second.py"
        second_file.write_text("def sub(one, two):\n    return one - two\n")
        complexity_probe.main(
            [str(first_file), str(second_file), "--repo-root", str(tmp_path)]
        )
        output = capsys.readouterr().out
        assert str(first_file) in output
        assert str(second_file) in output


class TestARangeNamesOneFile:
    """`<dir>:1-2` reported lines 1-2 of *every* file under the tree as one
    measurement — line numbers from one file cross-applied to all the others.
    A range names one function, so a directory is a target that cannot mean
    anything; the honest answer is to refuse it, not to answer confidently."""

    def _tree_with_two_files(self, tmp_path):
        (tmp_path / "sub").mkdir()
        (tmp_path / "File.py").write_text("def tiny(value):\n    return value\n")
        (tmp_path / "sub" / "Other.py").write_text("def other(value):\n    return 1\n")
        return tmp_path

    def test_a_range_on_a_directory_is_refused_with_a_reason(self, tmp_path, capsys):
        directory = self._tree_with_two_files(tmp_path)
        exit_code = complexity_probe.main([f"{directory}:1-2"])
        output = capsys.readouterr().out
        assert exit_code == 0
        assert "unverified" in output
        assert "is a directory" in output

    def test_it_does_not_report_the_range_against_every_file(self, tmp_path, capsys):
        directory = self._tree_with_two_files(tmp_path)
        complexity_probe.main([f"{directory}:1-2"])
        output = capsys.readouterr().out
        assert "tiny" not in output
        assert "other" not in output

    def test_the_refusal_is_data_in_the_artifact_too(self, tmp_path, capsys):
        """A consumer reading the payload must see the same refusal the
        transcript shows, not an empty `ran` measurement."""
        directory = self._tree_with_two_files(tmp_path)
        complexity_probe.main([f"{directory}:1-2", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["status"] == "unverified"
        assert "is a directory" in payload["reason"]
        assert payload["functions"] == []

    def test_the_same_directory_without_a_range_still_measures_it_all(
        self, tmp_path, capsys
    ):
        """The control: rejecting the range must not reject the directory."""
        directory = self._tree_with_two_files(tmp_path)
        complexity_probe.main([str(directory)])
        output = capsys.readouterr().out
        assert "tiny" in output
        assert "other" in output
