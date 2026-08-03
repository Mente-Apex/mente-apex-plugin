"""Thresholds come from the target repo or they do not exist. The plugin
ships no numbers of its own (spec §4.2)."""

import os

import pytest

from complexity_probe_thresholds import (
    CheckstyleThresholds,
    EslintThresholds,
    NullThresholds,
    PmdThresholds,
    RuffThresholds,
    discover_thresholds,
    no_thresholds_because,
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

    def test_eslint_numeric_severity_is_read(self, tmp_path):
        # ESLint's numeric severity form: 0 off, 1 warn, 2 error
        (tmp_path / "eslint.config.js").write_text(
            "export default [{ rules: { complexity: [2, 10] } }];\n"
        )
        thresholds = EslintThresholds().thresholds_for(tmp_path)
        assert thresholds.cyclomatic_complexity == 10

    def test_pmd_prefers_the_method_limit_over_the_class_limit(self, tmp_path):
        """A realistic ruleset declares both, class-level first. Reading the
        first textual match returned 80 — a per-class number compared against
        a per-function measurement, so the "worth a look" marker could never
        fire for any PMD repo while the artifact recorded 80 as the limit."""
        (tmp_path / "pmd-ruleset.xml").write_text(
            '<?xml version="1.0"?>\n'
            '<ruleset name="Custom" xmlns="http://pmd.sf.net/ruleset/1.0.0">\n'
            '  <rule ref="category/java/design.xml/CyclomaticComplexity">\n'
            "    <properties>\n"
            '      <property name="classReportLevel" value="80"/>\n'
            '      <property name="methodReportLevel" value="10"/>\n'
            "    </properties>\n"
            "  </rule>\n"
            "</ruleset>\n"
        )
        thresholds = PmdThresholds().thresholds_for(tmp_path)
        assert thresholds.cyclomatic_complexity == 10

    def test_pmd_reads_the_method_limit_from_the_rule_that_owns_it(self, tmp_path):
        """An earlier, unrelated rule must not lend its numbers to this one."""
        (tmp_path / "pmd-ruleset.xml").write_text(
            '<?xml version="1.0"?>\n'
            '<ruleset name="Custom" xmlns="http://pmd.sf.net/ruleset/1.0.0">\n'
            '  <rule ref="category/java/design.xml/NPathComplexity">\n'
            "    <properties>\n"
            '      <property name="methodReportLevel" value="200"/>\n'
            "    </properties>\n"
            "  </rule>\n"
            '  <rule ref="category/java/design.xml/CyclomaticComplexity">\n'
            "    <properties>\n"
            '      <property name="methodReportLevel" value="11"/>\n'
            "    </properties>\n"
            "  </rule>\n"
            "</ruleset>\n"
        )
        thresholds = PmdThresholds().thresholds_for(tmp_path)
        assert thresholds.cyclomatic_complexity == 11

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

    def test_checkstyle_does_not_misattribute_another_modules_threshold(self, tmp_path):
        # Regression: must not match properties from other modules (non-self-closed)
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

    def test_checkstyle_self_closing_module_yields_nothing(self, tmp_path):
        # Regression: self-closing CyclomaticComplexity must not pick up
        # following module's properties
        (tmp_path / "checkstyle.xml").write_text(
            '<?xml version="1.0"?>\n'
            '<module name="Checker">\n'
            '  <module name="CyclomaticComplexity"/>\n'
            '  <module name="MethodLength">\n'
            '    <property name="max" value="150"/>\n'
            "  </module>\n"
            "</module>\n"
        )
        assert CheckstyleThresholds().thresholds_for(tmp_path) is None

    def test_checkstyle_reads_treewalker_nested_module(self, tmp_path):
        # Real-world layout: CyclomaticComplexity nested inside TreeWalker
        (tmp_path / "checkstyle.xml").write_text(
            '<?xml version="1.0"?>\n'
            '<module name="Checker">\n'
            '  <module name="TreeWalker">\n'
            '    <module name="CyclomaticComplexity">\n'
            '      <property name="max" value="9"/>\n'
            "    </module>\n"
            "  </module>\n"
            "</module>\n"
        )
        thresholds = CheckstyleThresholds().thresholds_for(tmp_path)
        assert thresholds.cyclomatic_complexity == 9

    def test_malformed_config_is_absence_not_a_crash(self, tmp_path):
        (tmp_path / ".eslintrc.json").write_text("{not json")
        reading = EslintThresholds().thresholds_for(tmp_path)
        assert reading.cyclomatic_complexity is None
        assert reading.diagnostics

    def test_eslint_flat_config_cannot_be_parsed_yields_nothing(self, tmp_path):
        # Flat config is JavaScript; we cannot parse it perfectly, so we
        # conservatively return None rather than guess
        (tmp_path / "eslint.config.js").write_text(
            "export default calculateComplexityDynamically();\n"
        )
        assert EslintThresholds().thresholds_for(tmp_path) is None

    def test_eslint_commented_rule_beside_real_config_yields_nothing(self, tmp_path):
        # Regression: commented-out rule should not be extracted
        (tmp_path / "eslint.config.js").write_text(
            "export default [\n"
            "  {\n"
            '    // complexity: ["error", 10],  // old config\n'
            '    complexity: "off",\n'
            "  }\n"
            "];\n"
        )
        result = EslintThresholds().thresholds_for(tmp_path)
        assert result is None

    def test_eslint_pattern_inside_string_literal_yields_nothing(self, tmp_path):
        # Regression: complexity rule inside documentation string should
        # not be extracted
        (tmp_path / "eslint.config.js").write_text(
            "export default [\n"
            "  {\n"
            "    rules: {\n"
            '      complexity: "off",\n'
            "    },\n"
            '    // Documentation: use complexity: ["error", 10] for stricter rules\n'
            "  }\n"
            "];\n"
        )
        result = EslintThresholds().thresholds_for(tmp_path)
        assert result is None

    def test_eslint_url_on_earlier_line_extracts_real_rule(self, tmp_path):
        # Regression: URL string on earlier line with // must not affect
        # real rule on later line. Real-world: metadata with docsUrl.
        (tmp_path / "eslint.config.js").write_text(
            "export default [\n"
            "  {\n"
            '    meta: { docsUrl: "https://example.com/rules/complexity" },\n'
            "    rules: {\n"
            '      complexity: ["error", 12],\n'
            "    },\n"
            "  },\n"
            "];\n"
        )
        result = EslintThresholds().thresholds_for(tmp_path)
        assert result.cyclomatic_complexity == 12

    def test_eslint_url_same_line_as_rule_extracts_real_rule(self, tmp_path):
        # Regression: URL on same line as real rule must not blank the rule
        (tmp_path / "eslint.config.js").write_text(
            "export default [{\n"
            '  meta: { url: "https://example.com" }, rules: { complexity: ["error", 9] }\n'
            "}];\n"
        )
        result = EslintThresholds().thresholds_for(tmp_path)
        assert result.cyclomatic_complexity == 9

    def test_eslint_genuine_comment_with_url_is_stripped(self, tmp_path):
        # Real comment containing URL is stripped; rule works
        (tmp_path / "eslint.config.js").write_text(
            "export default [\n"
            "  {\n"
            "    // See https://example.com/rules for details\n"
            "    rules: {\n"
            '      complexity: ["error", 11],\n'
            "    },\n"
            "  },\n"
            "];\n"
        )
        result = EslintThresholds().thresholds_for(tmp_path)
        assert result.cyclomatic_complexity == 11

    def test_eslint_rule_inside_backtick_template_literal_yields_nothing(
        self, tmp_path
    ):
        # Rule inside backtick string should not be extracted
        (tmp_path / "eslint.config.js").write_text(
            "export default [\n"
            "  {\n"
            '    docstring: `complexity: ["error", 10]`,\n'
            "    rules: {\n"
            '      complexity: "off",\n'
            "    },\n"
            "  },\n"
            "];\n"
        )
        result = EslintThresholds().thresholds_for(tmp_path)
        assert result is None

    def test_eslint_escaped_quote_before_pattern_handled_correctly(self, tmp_path):
        # Escaped quote should not end string prematurely
        (tmp_path / "eslint.config.js").write_text(
            "export default [\n"
            "  {\n"
            '    text: "\\"quoted\\" text",\n'
            "    rules: {\n"
            '      complexity: ["error", 14],\n'
            "    },\n"
            "  },\n"
            "];\n"
        )
        result = EslintThresholds().thresholds_for(tmp_path)
        assert result.cyclomatic_complexity == 14

    def test_eslint_variable_severity_yields_nothing(self, tmp_path):
        # A severity that is an identifier cannot be read statically, so the
        # array cannot be trusted to mean what it looks like
        (tmp_path / "eslint.config.js").write_text(
            "export default [{ rules: { complexity: [errorLevel, 10] } }];\n"
        )
        assert EslintThresholds().thresholds_for(tmp_path) is None

    def test_eslint_spread_severity_yields_nothing(self, tmp_path):
        # A spread can contribute any number of elements, so the 10 is not
        # provably the maximum
        (tmp_path / "eslint.config.js").write_text(
            "export default [{ rules: { complexity: [...baseRule, 10] } }];\n"
        )
        assert EslintThresholds().thresholds_for(tmp_path) is None

    def test_eslint_template_literal_severity_yields_nothing(self, tmp_path):
        # A template literal may interpolate; it is not a literal severity
        (tmp_path / "eslint.config.js").write_text(
            "export default [{ rules: { complexity: [`error`, 10] } }];\n"
        )
        assert EslintThresholds().thresholds_for(tmp_path) is None

    def test_eslint_regex_literal_containing_a_quote_does_not_hide_the_rule(
        self, tmp_path
    ):
        # Regression: a lone quote inside a regex character class must not
        # open a phantom string that swallows the rest of the file
        (tmp_path / "eslint.config.js").write_text(
            "const pattern = /[\"']/;\n"
            'export default [{ rules: { complexity: ["error", 13] } }];\n'
        )
        thresholds = EslintThresholds().thresholds_for(tmp_path)
        assert thresholds.cyclomatic_complexity == 13

    def test_eslint_division_is_not_mistaken_for_a_regex_literal(self, tmp_path):
        # The regex heuristic must not overreach: a `/` after a value divides,
        # and blanking from there would swallow the rule sharing its line
        (tmp_path / "eslint.config.js").write_text(
            "const budget = 24;\n"
            "export default [\n"
            '  { rules: { "max-lines": budget / 2, complexity: ["error", 8] } },\n'
            "];\n"
        )
        thresholds = EslintThresholds().thresholds_for(tmp_path)
        assert thresholds.cyclomatic_complexity == 8

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

    def test_pmd_class_report_level_alone_is_not_a_per_function_limit(self, tmp_path):
        """A ruleset declaring only the class-level limit declares no limit a
        function can breach. Returning the class number would be an invented
        per-function threshold, and a wrong number costs more than an absent
        one."""
        (tmp_path / "pmd-ruleset.xml").write_text(
            '<?xml version="1.0"?>\n'
            '<ruleset name="Custom" xmlns="http://pmd.sf.net/ruleset/1.0.0">\n'
            '  <rule ref="category/java/design.xml/CyclomaticComplexity">\n'
            "    <properties>\n"
            '      <property name="classReportLevel" value="80"/>\n'
            "    </properties>\n"
            "  </rule>\n"
            "</ruleset>\n"
        )
        assert PmdThresholds().thresholds_for(tmp_path) is None

    def test_pmd_malformed_xml_is_absence_not_a_crash(self, tmp_path):
        (tmp_path / "pmd-ruleset.xml").write_text(
            '<?xml version="1.0"?>\n<ruleset><rule ref="CyclomaticComplexity">\n'
        )
        reading = PmdThresholds().thresholds_for(tmp_path)
        assert reading.cyclomatic_complexity is None
        assert any(
            "pmd-ruleset.xml" in diagnostic for diagnostic in reading.diagnostics
        )

    def test_pmd_non_numeric_report_level_is_absence(self, tmp_path):
        (tmp_path / "pmd-ruleset.xml").write_text(
            '<?xml version="1.0"?>\n'
            "<ruleset>\n"
            '  <rule ref="category/java/design.xml/CyclomaticComplexity">\n'
            '    <property name="methodReportLevel" value="ten"/>\n'
            "  </rule>\n"
            "</ruleset>\n"
        )
        reading = PmdThresholds().thresholds_for(tmp_path)
        assert reading.cyclomatic_complexity is None
        assert any("ten" in diagnostic for diagnostic in reading.diagnostics)


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

    def test_pmd_wins_over_ruff_in_default_registry_order(self, tmp_path):
        # Checkstyle missing; PMD has a threshold → PMD wins over Ruff
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
        assert thresholds.cyclomatic_complexity == 10

    def test_repo_root_checkstyle_wins_over_gradle_location(self, tmp_path):
        # Both repo-root and Gradle-path configs exist → repo-root wins
        (tmp_path / "checkstyle.xml").write_text(
            '<?xml version="1.0"?>\n'
            '<module name="Checker">\n'
            '  <module name="CyclomaticComplexity">\n'
            '    <property name="max" value="11"/>\n'
            "  </module>\n"
            "</module>\n"
        )
        (tmp_path / "config" / "checkstyle").mkdir(parents=True)
        (tmp_path / "config" / "checkstyle" / "checkstyle.xml").write_text(
            '<?xml version="1.0"?>\n'
            '<module name="Checker">\n'
            '  <module name="CyclomaticComplexity">\n'
            '    <property name="max" value="9"/>\n'
            "  </module>\n"
            "</module>\n"
        )
        thresholds = discover_thresholds(tmp_path)
        assert thresholds.cyclomatic_complexity == 11

    def test_ruff_wins_over_eslint_in_default_registry_order(self, tmp_path):
        # Both Ruff and ESLint configs exist → Ruff wins
        (tmp_path / "pyproject.toml").write_text(
            "[tool.ruff.lint.mccabe]\nmax-complexity = 7\n"
        )
        (tmp_path / ".eslintrc.json").write_text(
            '{"rules": {"complexity": ["error", 5]}}'
        )
        thresholds = discover_thresholds(tmp_path)
        assert thresholds.cyclomatic_complexity == 7


class TestAMalformedConfigIsAbsenceNeverACrash:
    """Every source reads a file some other tool owns, so a repo with a typo in
    that file is still owed a measurement. Before this, three shapes escaped as
    tracebacks and took exit 1 — the code this branch reserves for a blocking
    gate verdict — turning "the gate is a reporter, not a blocker" into a claim
    a config typo could falsify.

    Absence, though, has to say why. A config that could not be read reports
    no limit *and* names the cause: reporting it as the plain "none declared" a
    repo with no config gets is the silence rule 1 forbids, and it is how a
    typo'd threshold gets ignored with nobody told."""

    def test_ruff_non_integer_max_complexity_is_absence_that_says_why(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            '[tool.ruff.lint.mccabe]\nmax-complexity = "ten"\n'
        )
        reading = RuffThresholds().thresholds_for(tmp_path)
        assert reading.cyclomatic_complexity is None
        assert any("ten" in diagnostic for diagnostic in reading.diagnostics)

    def test_ruff_falls_through_a_broken_table_to_the_legacy_one(self, tmp_path):
        """An unreadable value in the current table is absence *for that
        table*, not for the file: a repo that still declares a usable legacy
        limit gets it."""
        (tmp_path / "pyproject.toml").write_text(
            '[tool.ruff.lint.mccabe]\nmax-complexity = "ten"\n'
            "[tool.ruff.mccabe]\nmax-complexity = 7\n"
        )
        thresholds = RuffThresholds().thresholds_for(tmp_path)
        assert thresholds.cyclomatic_complexity == 7

    def test_ruff_unexpected_table_shape_is_absence(self, tmp_path):
        """`tool.ruff` is a string here, so the old `.get()` chain would raise
        AttributeError on a perfectly valid TOML document."""
        (tmp_path / "pyproject.toml").write_text('[tool]\nruff = "please"\n')
        assert RuffThresholds().thresholds_for(tmp_path) is None

    def test_ruff_unreadable_pyproject_is_absence_that_says_why(self, tmp_path):
        if os.geteuid() == 0:
            pytest.skip("running as root: file mode 000 is still readable")
        config_path = tmp_path / "pyproject.toml"
        config_path.write_text("[tool.ruff.lint.mccabe]\nmax-complexity = 8\n")
        config_path.chmod(0o000)
        try:
            reading = RuffThresholds().thresholds_for(tmp_path)
        finally:
            config_path.chmod(0o600)
        assert reading.cyclomatic_complexity is None
        assert any(
            "pyproject.toml" in diagnostic and "PermissionError" in diagnostic
            for diagnostic in reading.diagnostics
        )

    def test_eslint_legacy_json_root_that_is_not_an_object_says_why(self, tmp_path):
        """`[1,2,3]` is valid JSON and not an ESLint config. Asking a list for
        `rules` was an AttributeError all the way to the user."""
        (tmp_path / ".eslintrc.json").write_text("[1,2,3]\n")
        reading = EslintThresholds().thresholds_for(tmp_path)
        assert reading.cyclomatic_complexity is None
        assert any(".eslintrc.json" in diagnostic for diagnostic in reading.diagnostics)

    def test_eslint_legacy_rules_that_is_not_an_object_says_why(self, tmp_path):
        (tmp_path / ".eslintrc.json").write_text('{"rules": "all of them"}\n')
        reading = EslintThresholds().thresholds_for(tmp_path)
        assert reading.cyclomatic_complexity is None
        assert any("rules" in diagnostic for diagnostic in reading.diagnostics)

    def test_eslint_legacy_non_integer_limit_says_why(self, tmp_path):
        """The object form is a declared limit this reader cannot use. Silently
        measuring against no threshold leaves the repo believing its 10 is in
        force."""
        (tmp_path / ".eslintrc.json").write_text(
            '{"rules": {"complexity": ["error", {"max": 10}]}}\n'
        )
        reading = EslintThresholds().thresholds_for(tmp_path)
        assert reading.cyclomatic_complexity is None
        assert reading.diagnostics

    def test_eslint_a_config_with_no_complexity_rule_is_plain_absence(self, tmp_path):
        """The control. Most configs set no complexity rule at all, and that is
        an ordinary repo, not a broken one — it must not produce a diagnostic."""
        (tmp_path / ".eslintrc.json").write_text('{"rules": {"eqeqeq": "error"}}\n')
        assert EslintThresholds().thresholds_for(tmp_path) is None

    def test_checkstyle_malformed_xml_is_absence_that_says_why(self, tmp_path):
        """Checkstyle is consulted *first*, so an unreported break here is the
        one that costs a whole toolchain its threshold."""
        (tmp_path / "checkstyle.xml").write_text(
            '<?xml version="1.0"?>\n<module name="Checker">\n'
        )
        reading = CheckstyleThresholds().thresholds_for(tmp_path)
        assert reading.cyclomatic_complexity is None
        assert any("checkstyle.xml" in diagnostic for diagnostic in reading.diagnostics)

    def test_checkstyle_non_numeric_max_is_absence_that_says_why(self, tmp_path):
        (tmp_path / "checkstyle.xml").write_text(
            '<?xml version="1.0"?>\n'
            '<module name="Checker">\n'
            '  <module name="CyclomaticComplexity">\n'
            '    <property name="max" value="ten"/>\n'
            "  </module>\n"
            "</module>\n"
        )
        reading = CheckstyleThresholds().thresholds_for(tmp_path)
        assert reading.cyclomatic_complexity is None
        assert any("ten" in diagnostic for diagnostic in reading.diagnostics)

    def test_eslint_flat_config_declaring_two_maximums_says_why(self, tmp_path):
        """Two readable candidates that disagree. The repo declared something;
        this reader cannot tell which number governs the code being measured,
        and saying nothing would leave the repo believing one of them is in
        force."""
        (tmp_path / "eslint.config.js").write_text(
            "export default [\n"
            "  { rules: { complexity: ['error', 10] } },\n"
            "  { rules: { complexity: ['error', 12] } },\n"
            "];\n"
        )
        reading = EslintThresholds().thresholds_for(tmp_path)
        assert reading.cyclomatic_complexity is None
        assert any("10" in diagnostic for diagnostic in reading.diagnostics)
        assert any("12" in diagnostic for diagnostic in reading.diagnostics)

    def test_eslint_unreadable_flat_config_says_why(self, tmp_path):
        if os.geteuid() == 0:
            pytest.skip("running as root: file mode 000 is still readable")
        config_path = tmp_path / "eslint.config.js"
        config_path.write_text("export default [{ rules: { complexity: [1, 10] } }];\n")
        config_path.chmod(0o000)
        try:
            reading = EslintThresholds().thresholds_for(tmp_path)
        finally:
            config_path.chmod(0o600)
        assert reading.cyclomatic_complexity is None
        assert any(
            "eslint.config.js" in diagnostic for diagnostic in reading.diagnostics
        )

    def test_eslint_flat_config_with_no_rule_at_all_is_plain_absence(self, tmp_path):
        """The control. Flat config is JavaScript and most of them set no
        complexity rule, so "I extracted nothing" must stay quiet."""
        (tmp_path / "eslint.config.js").write_text(
            "export default calculateComplexityDynamically();\n"
        )
        assert EslintThresholds().thresholds_for(tmp_path) is None

    def test_eslint_unreadable_legacy_config_is_absence_that_says_why(self, tmp_path):
        if os.geteuid() == 0:
            pytest.skip("running as root: file mode 000 is still readable")
        config_path = tmp_path / ".eslintrc.json"
        config_path.write_text('{"rules": {"complexity": ["error", 10]}}')
        config_path.chmod(0o000)
        try:
            reading = EslintThresholds().thresholds_for(tmp_path)
        finally:
            config_path.chmod(0o600)
        assert reading.cyclomatic_complexity is None
        assert any(
            "PermissionError" in diagnostic for diagnostic in reading.diagnostics
        )


class TestDiscoveryTellsTheTwoAbsencesApart:
    """ "This repo declares no limit" and "your config has a typo so nothing is"
    used to read identically, so a repo whose declared threshold was being
    ignored got no signal at all — the same silence the probe exists to catch,
    inside the module whose whole job is reading declared limits.

    `diagnostics` is what tells them apart. `source` does not: it names where
    the limit in force came from, which in both of these cases is nowhere."""

    def test_a_repo_with_no_config_at_all_still_reads_none_declared(self, tmp_path):
        thresholds = discover_thresholds(tmp_path)
        assert thresholds.source == "none declared"
        assert thresholds.diagnostics == ()

    def test_a_typo_is_not_reported_as_declaring_nothing(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            '[tool.ruff.lint.mccabe]\nmax-complexity = "ten"\n'
        )
        thresholds = discover_thresholds(tmp_path)
        assert thresholds.cyclomatic_complexity is None
        assert any("ten" in diagnostic for diagnostic in thresholds.diagnostics)

    def test_an_absence_with_no_cause_at_all_cannot_be_built(self):
        """`NO_THRESHOLDS` is the honest way to say "nothing was declared".
        This function is for the other absence, so a call that names no cause
        is the silence it exists to end and must not typecheck at runtime."""
        with pytest.raises(TypeError):
            no_thresholds_because()

    def test_source_never_restates_a_diagnostic(self, tmp_path):
        """`source` used to be `"none readable — " + "; ".join(diagnostics)`,
        so it meant one of two things depending on the field beside it and a
        reader had to check `cyclomatic_complexity` to know which. Absence has
        one wording now, whatever caused it."""
        (tmp_path / "pyproject.toml").write_text(
            '[tool.ruff.lint.mccabe]\nmax-complexity = "ten"\n'
        )
        thresholds = discover_thresholds(tmp_path)
        assert thresholds.source == "none declared"
        assert thresholds.diagnostics
        assert "ten" not in thresholds.source

    def test_an_unreadable_config_does_not_hide_a_later_declared_limit(self, tmp_path):
        """A broken ruff table must not cost the repo its ESLint limit. The
        number is used, and the typo is still reported."""
        (tmp_path / "pyproject.toml").write_text(
            '[tool.ruff.lint.mccabe]\nmax-complexity = "ten"\n'
        )
        (tmp_path / ".eslintrc.json").write_text(
            '{"rules": {"complexity": ["error", 9]}}'
        )
        thresholds = discover_thresholds(tmp_path)
        assert thresholds.cyclomatic_complexity == 9
        assert thresholds.source == ".eslintrc.json"
        assert any("ten" in diagnostic for diagnostic in thresholds.diagnostics)

    def test_a_typo_after_the_winning_source_is_reported_too(self, tmp_path):
        """The same repo with its tools the other way round. Stopping at the
        winner made *which* typos got reported an accident of discovery order,
        so a Java repo with a working checkstyle.xml was told nothing about the
        broken ruff table underneath it — the silence, restored, for everyone
        who ordered their tools the other way."""
        (tmp_path / "checkstyle.xml").write_text(
            '<?xml version="1.0"?>\n'
            '<module name="Checker">\n'
            '  <module name="CyclomaticComplexity">\n'
            '    <property name="max" value="7"/>\n'
            "  </module>\n"
            "</module>\n"
        )
        (tmp_path / "pyproject.toml").write_text(
            '[tool.ruff.lint.mccabe]\nmax-complexity = "ten"\n'
        )
        thresholds = discover_thresholds(tmp_path)
        assert thresholds.cyclomatic_complexity == 7
        assert thresholds.source == "checkstyle.xml"
        assert any("ten" in diagnostic for diagnostic in thresholds.diagnostics)

    def test_two_unreadable_configs_both_reach_the_report(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            '[tool.ruff.lint.mccabe]\nmax-complexity = "ten"\n'
        )
        (tmp_path / ".eslintrc.json").write_text("[1,2,3]\n")
        thresholds = discover_thresholds(tmp_path)
        assert len(thresholds.diagnostics) == 2
        assert any(
            "pyproject.toml" in diagnostic for diagnostic in thresholds.diagnostics
        )
        assert any(
            ".eslintrc.json" in diagnostic for diagnostic in thresholds.diagnostics
        )


class TestADisabledRuleDeclaresNoLimit:
    """`["off", 10]` is a repo saying "do not run this rule". The 10 beside it
    is a leftover, not a declared limit — reporting it made the probe point at
    breaches of a threshold the project had switched off. The flat and legacy
    paths have always agreed on what a severity means and must keep agreeing,
    so both are pinned here."""

    def test_flat_config_off_severity_yields_nothing(self, tmp_path):
        (tmp_path / "eslint.config.js").write_text(
            "export default [\n" "  { rules: { complexity: ['off', 10] } },\n" "];\n"
        )
        assert EslintThresholds().thresholds_for(tmp_path) is None

    def test_flat_config_zero_severity_yields_nothing(self, tmp_path):
        (tmp_path / "eslint.config.js").write_text(
            "export default [\n  { rules: { complexity: [0, 10] } },\n];\n"
        )
        assert EslintThresholds().thresholds_for(tmp_path) is None

    def test_legacy_config_off_severity_yields_nothing(self, tmp_path):
        (tmp_path / ".eslintrc.json").write_text(
            '{"rules": {"complexity": ["off", 10]}}'
        )
        assert EslintThresholds().thresholds_for(tmp_path) is None

    def test_legacy_config_zero_severity_yields_nothing(self, tmp_path):
        (tmp_path / ".eslintrc.json").write_text('{"rules": {"complexity": [0, 10]}}')
        assert EslintThresholds().thresholds_for(tmp_path) is None

    def test_an_enabled_rule_beside_a_disabled_one_is_still_read(self, tmp_path):
        """Skipping a disabled rule must not also discard the live one."""
        (tmp_path / "eslint.config.js").write_text(
            "export default [\n"
            "  { rules: { complexity: ['off', 10] } },\n"
            "  { files: ['src/**'], rules: { complexity: ['error', 12] } },\n"
            "];\n"
        )
        thresholds = EslintThresholds().thresholds_for(tmp_path)
        assert thresholds.cyclomatic_complexity == 12


class TestArrowFunctionsBeforeTheRule:
    def test_a_regex_literal_after_an_arrow_does_not_swallow_the_rule(self, tmp_path):
        """`=>` ends with `>`, which was missing from the regex-literal
        preceders — so `/["']/` read as division and its quote characters
        opened a string that swallowed the rest of the file, including the
        real rule. Arrow functions are near-universal in eslint.config.js."""
        (tmp_path / "eslint.config.js").write_text(
            "const hasQuote = (value) => /[\"']/.test(value);\n"
            "export default [\n"
            "  { rules: { complexity: ['error', 12] } },\n"
            "];\n"
        )
        thresholds = EslintThresholds().thresholds_for(tmp_path)
        assert thresholds.cyclomatic_complexity == 12

    def test_the_same_file_without_the_arrow_already_worked(self, tmp_path):
        """The control: the defect was the arrow, not the regex literal."""
        (tmp_path / "eslint.config.js").write_text(
            "export default [\n" "  { rules: { complexity: ['error', 12] } },\n" "];\n"
        )
        thresholds = EslintThresholds().thresholds_for(tmp_path)
        assert thresholds.cyclomatic_complexity == 12
