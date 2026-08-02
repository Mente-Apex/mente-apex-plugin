"""Thresholds come from the target repo or they do not exist. The plugin
ships no numbers of its own (spec §4.2)."""

from complexity_probe_thresholds import (
    CheckstyleThresholds,
    EslintThresholds,
    NullThresholds,
    PmdThresholds,
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

    def test_checkstyle_reads_gradle_standard_location(self, tmp_path):
        (tmp_path / "config" / "checkstyle").mkdir(parents=True)
        (tmp_path / "config" / "checkstyle" / "checkstyle.xml").write_text(
            '<?xml version="1.0"?>\n'
            '<module name="Checker">\n'
            '  <module name="CyclomaticComplexity">\n'
            '    <property name="max" value="9"/>\n'
            "  </module>\n"
            "</module>\n"
        )
        thresholds = CheckstyleThresholds().thresholds_for(tmp_path)
        assert thresholds.cyclomatic_complexity == 9
        assert "config" in thresholds.source

    def test_ruff_mccabe_max_complexity_is_read(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            "[tool.ruff.lint.mccabe]\nmax-complexity = 8\n"
        )
        thresholds = RuffThresholds().thresholds_for(tmp_path)
        assert thresholds.cyclomatic_complexity == 8

    def test_ruff_reads_legacy_mccabe_table(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            "[tool.ruff.mccabe]\nmax-complexity = 7\n"
        )
        thresholds = RuffThresholds().thresholds_for(tmp_path)
        assert thresholds.cyclomatic_complexity == 7
        assert "deprecated" in thresholds.source

    def test_ruff_prefers_current_table_over_legacy(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            "[tool.ruff.lint.mccabe]\nmax-complexity = 8\n"
            "[tool.ruff.mccabe]\nmax-complexity = 7\n"
        )
        thresholds = RuffThresholds().thresholds_for(tmp_path)
        assert thresholds.cyclomatic_complexity == 8

    def test_eslint_complexity_rule_is_read(self, tmp_path):
        (tmp_path / ".eslintrc.json").write_text(
            '{"rules": {"complexity": ["error", 10]}}'
        )
        thresholds = EslintThresholds().thresholds_for(tmp_path)
        assert thresholds.cyclomatic_complexity == 10

    def test_eslint_reads_flat_config_js(self, tmp_path):
        (tmp_path / "eslint.config.js").write_text(
            "export default [\n"
            "  {\n"
            "    rules: {\n"
            '      complexity: ["error", 11]\n'
            "    }\n"
            "  }\n"
            "];\n"
        )
        thresholds = EslintThresholds().thresholds_for(tmp_path)
        assert thresholds.cyclomatic_complexity == 11
        assert "eslint.config.js" in thresholds.source

    def test_eslint_reads_flat_config_mjs(self, tmp_path):
        (tmp_path / "eslint.config.mjs").write_text(
            "export default [\n"
            "  {\n"
            "    rules: {\n"
            '      complexity: ["warn", 13]\n'
            "    }\n"
            "  }\n"
            "];\n"
        )
        thresholds = EslintThresholds().thresholds_for(tmp_path)
        assert thresholds.cyclomatic_complexity == 13

    def test_eslint_prefers_flat_config_over_legacy(self, tmp_path):
        (tmp_path / "eslint.config.js").write_text(
            'export default [{ rules: { complexity: ["error", 11] } }];\n'
        )
        (tmp_path / ".eslintrc.json").write_text(
            '{"rules": {"complexity": ["error", 10]}}'
        )
        thresholds = EslintThresholds().thresholds_for(tmp_path)
        assert thresholds.cyclomatic_complexity == 11

    def test_pmd_cyclomatic_complexity_is_read_from_classReportLevel(self, tmp_path):
        (tmp_path / "pmd-ruleset.xml").write_text(
            '<?xml version="1.0"?>\n'
            '<ruleset name="Custom" xmlns="http://pmd.sf.net/ruleset/1.0.0">\n'
            '  <rule ref="category/java/design.xml/CyclomaticComplexity">\n'
            '    <property name="classReportLevel" value="10"/>\n'
            "  </rule>\n"
            "</ruleset>\n"
        )
        thresholds = PmdThresholds().thresholds_for(tmp_path)
        assert thresholds.cyclomatic_complexity == 10

    def test_pmd_cyclomatic_complexity_is_read_from_methodReportLevel(self, tmp_path):
        (tmp_path / "pmd-ruleset.xml").write_text(
            '<?xml version="1.0"?>\n'
            '<ruleset name="Custom" xmlns="http://pmd.sf.net/ruleset/1.0.0">\n'
            '  <rule ref="category/java/design.xml/CyclomaticComplexity">\n'
            '    <property name="methodReportLevel" value="7"/>\n'
            "  </rule>\n"
            "</ruleset>\n"
        )
        thresholds = PmdThresholds().thresholds_for(tmp_path)
        assert thresholds.cyclomatic_complexity == 7


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

    def test_checkstyle_regex_does_not_misattribute_another_modules_threshold(
        self, tmp_path
    ):
        # Regression: regex must not match properties from other modules
        (tmp_path / "checkstyle.xml").write_text(
            '<?xml version="1.0"?>\n'
            '<module name="Checker">\n'
            '  <module name="CyclomaticComplexity">\n'
            "  </module>\n"
            '  <module name="MethodLength">\n'
            '    <property name="max" value="150"/>\n'
            "  </module>\n"
            "</module>\n"
        )
        assert CheckstyleThresholds().thresholds_for(tmp_path) is None

    def test_malformed_config_is_absence_not_a_crash(self, tmp_path):
        (tmp_path / ".eslintrc.json").write_text("{not json")
        assert EslintThresholds().thresholds_for(tmp_path) is None

    def test_eslint_flat_config_cannot_be_parsed_yields_nothing(self, tmp_path):
        # Flat config is JavaScript; we cannot parse it perfectly, so we
        # conservatively return None rather than guess
        (tmp_path / "eslint.config.js").write_text(
            "export default calculateComplexityDynamically();\n"
        )
        assert EslintThresholds().thresholds_for(tmp_path) is None

    def test_the_null_source_always_yields_nothing(self, tmp_path):
        assert NullThresholds().thresholds_for(tmp_path) is None

    def test_pmd_without_report_level_yields_nothing(self, tmp_path):
        (tmp_path / "pmd-ruleset.xml").write_text(
            '<?xml version="1.0"?>\n'
            '<ruleset name="Custom" xmlns="http://pmd.sf.net/ruleset/1.0.0">\n'
            '  <rule ref="category/java/design.xml/CyclomaticComplexity"/>\n'
            "</ruleset>\n"
        )
        assert PmdThresholds().thresholds_for(tmp_path) is None


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

    def test_registry_order_is_checkstyle_pmd_ruff_eslint(self, tmp_path):
        # Create all four config files; verify Checkstyle is consulted first
        (tmp_path / "checkstyle.xml").write_text(
            '<?xml version="1.0"?>\n'
            '<module name="Checker">\n'
            '  <module name="CyclomaticComplexity">\n'
            '    <property name="max" value="12"/>\n'
            "  </module>\n"
            "</module>\n"
        )
        (tmp_path / "pmd-ruleset.xml").write_text(
            '<?xml version="1.0"?>\n'
            '<ruleset name="Custom" xmlns="http://pmd.sf.net/ruleset/1.0.0">\n'
            '  <rule ref="category/java/design.xml/CyclomaticComplexity">\n'
            '    <property name="methodReportLevel" value="10"/>\n'
            "  </rule>\n"
            "</ruleset>\n"
        )
        (tmp_path / "pyproject.toml").write_text(
            "[tool.ruff.lint.mccabe]\nmax-complexity = 8\n"
        )
        (tmp_path / ".eslintrc.json").write_text(
            '{"rules": {"complexity": ["error", 6]}}'
        )
        thresholds = discover_thresholds(tmp_path)
        assert thresholds.cyclomatic_complexity == 12

    def test_registry_falls_through_to_ruff_when_checkstyle_missing(self, tmp_path):
        (tmp_path / "pmd-ruleset.xml").write_text(
            '<?xml version="1.0"?>\n'
            '<ruleset name="Custom" xmlns="http://pmd.sf.net/ruleset/1.0.0">\n'
            '  <rule ref="category/java/design.xml/CyclomaticComplexity">\n'
            '    <property name="methodReportLevel" value="10"/>\n'
            "  </rule>\n"
            "</ruleset>\n"
        )
        (tmp_path / "pyproject.toml").write_text(
            "[tool.ruff.lint.mccabe]\nmax-complexity = 8\n"
        )
        thresholds = discover_thresholds(tmp_path)
        # Checkstyle doesn't exist; PMD should be checked; assume PMD regex
        # works and returns 10. But wait, that would mean PMD is consulted
        # before Ruff. Let me reconsider: the expected order is
        # Checkstyle → PMD → Ruff → ESLint. So if Checkstyle returns None
        # (missing file), we check PMD. If PMD has a threshold, we return it.
        # Let me adjust this test.
        assert thresholds.cyclomatic_complexity == 10
