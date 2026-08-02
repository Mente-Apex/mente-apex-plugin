"""Thresholds come from the target repo or they do not exist. The plugin
ships no numbers of its own (spec §4.2)."""

from complexity_probe_thresholds import (
    CheckstyleThresholds,
    EslintThresholds,
    NullThresholds,
    RuffThresholds,
    discover_thresholds,
)


class TestReadingWhatTheRepoDeclares:
    def test_checkstyle_cyclomatic_complexity_is_read(self, tmp_path):
        (tmp_path / "checkstyle.xml").write_text(
            '<?xml version="1.0"?>\n'
            '<module name="Checker">\n'
            '  <module name="CyclomaticComplexity">\n'
            '    <property name="max" value="12"/>\n'
            "  </module>\n"
            "</module>\n"
        )
        thresholds = CheckstyleThresholds().thresholds_for(tmp_path)
        assert thresholds.cyclomatic_complexity == 12
        assert "checkstyle" in thresholds.source

    def test_ruff_mccabe_max_complexity_is_read(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            "[tool.ruff.lint.mccabe]\nmax-complexity = 8\n"
        )
        thresholds = RuffThresholds().thresholds_for(tmp_path)
        assert thresholds.cyclomatic_complexity == 8

    def test_eslint_complexity_rule_is_read(self, tmp_path):
        (tmp_path / ".eslintrc.json").write_text(
            '{"rules": {"complexity": ["error", 10]}}'
        )
        thresholds = EslintThresholds().thresholds_for(tmp_path)
        assert thresholds.cyclomatic_complexity == 10


class TestAbsence:
    def test_a_repo_declaring_nothing_yields_no_number(self, tmp_path):
        thresholds = discover_thresholds(tmp_path)
        assert thresholds.cyclomatic_complexity is None
        assert "none declared" in thresholds.source

    def test_checkstyle_without_the_rule_yields_nothing(self, tmp_path):
        (tmp_path / "checkstyle.xml").write_text(
            '<?xml version="1.0"?>\n<module name="Checker"/>\n'
        )
        assert CheckstyleThresholds().thresholds_for(tmp_path) is None

    def test_malformed_config_is_absence_not_a_crash(self, tmp_path):
        (tmp_path / ".eslintrc.json").write_text("{not json")
        assert EslintThresholds().thresholds_for(tmp_path) is None

    def test_the_null_source_always_yields_nothing(self, tmp_path):
        assert NullThresholds().thresholds_for(tmp_path) is None


class TestDiscoveryOrder:
    def test_the_first_source_that_declares_a_number_wins(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            "[tool.ruff.lint.mccabe]\nmax-complexity = 8\n"
        )
        (tmp_path / ".eslintrc.json").write_text(
            '{"rules": {"complexity": ["error", 10]}}'
        )
        thresholds = discover_thresholds(
            tmp_path, sources=(RuffThresholds(), EslintThresholds())
        )
        assert thresholds.cyclomatic_complexity == 8

    def test_adding_a_source_needs_no_edit_to_discovery(self, tmp_path):
        class FakeSource:
            def thresholds_for(self, repo_root):
                from complexity_probe_thresholds import Thresholds

                return Thresholds(cyclomatic_complexity=99, source="fake")

        thresholds = discover_thresholds(tmp_path, sources=(FakeSource(),))
        assert thresholds.cyclomatic_complexity == 99
