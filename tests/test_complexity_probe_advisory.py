"""Advice makes `unverified` actionable. It never blocks, never invents a
version, and distinguishes install from upgrade."""

import re

import pytest

from complexity_probe_advisory import (
    ABSENT,
    TOO_OLD,
    advice_for,
    detect_build_system,
)


class TestDetectingTheBuildSystem:
    def test_gradle_kotlin_dsl(self, tmp_path):
        (tmp_path / "build.gradle.kts").write_text("plugins { java }")
        assert detect_build_system(tmp_path) == "gradle-kotlin"

    def test_gradle_groovy_dsl(self, tmp_path):
        (tmp_path / "build.gradle").write_text("plugins { id 'java' }")
        assert detect_build_system(tmp_path) == "gradle-groovy"

    def test_maven(self, tmp_path):
        (tmp_path / "pom.xml").write_text("<project/>")
        assert detect_build_system(tmp_path) == "maven"

    def test_nothing_recognizable(self, tmp_path):
        assert detect_build_system(tmp_path) == "unknown"

    def test_kotlin_dsl_wins_when_both_gradle_files_exist(self, tmp_path):
        (tmp_path / "build.gradle").write_text("")
        (tmp_path / "build.gradle.kts").write_text("")
        assert detect_build_system(tmp_path) == "gradle-kotlin"


class TestAdviceContent:
    def test_gradle_kotlin_archunit_names_the_test_dependency(self, tmp_path):
        (tmp_path / "build.gradle.kts").write_text("")
        advice = advice_for("archunit", tmp_path, reason=ABSENT)
        assert "testImplementation" in advice.snippet
        assert "com.tngtech.archunit" in advice.snippet

    def test_maven_pit_names_the_plugin(self, tmp_path):
        (tmp_path / "pom.xml").write_text("<project/>")
        advice = advice_for("pit", tmp_path, reason=ABSENT)
        assert "pitest-maven" in advice.snippet

    def test_jacoco_on_gradle_is_the_built_in_plugin(self, tmp_path):
        (tmp_path / "build.gradle.kts").write_text("")
        advice = advice_for("jacoco", tmp_path, reason=ABSENT)
        assert "jacoco" in advice.snippet

    @pytest.mark.parametrize(
        "tool,build_system,marker",
        [
            ("archunit", "gradle-kotlin", "com.tngtech.archunit"),
            ("archunit", "gradle-groovy", "com.tngtech.archunit"),
            ("archunit", "maven", "com.tngtech.archunit"),
            ("pit", "gradle-kotlin", "pitest"),
            ("pit", "gradle-groovy", "pitest"),
            ("pit", "maven", "pitest"),
            ("jacoco", "gradle-kotlin", "jacoco"),
            ("jacoco", "gradle-groovy", "jacoco"),
            ("jacoco", "maven", "jacoco"),
            ("checkstyle", "gradle-kotlin", "checkstyle"),
            ("checkstyle", "gradle-groovy", "checkstyle"),
            ("checkstyle", "maven", "maven-checkstyle"),
            ("pmd", "gradle-kotlin", "pmd"),
            ("pmd", "gradle-groovy", "pmd"),
            ("pmd", "maven", "maven-pmd"),
            ("spotbugs", "gradle-kotlin", "spotbugs"),
            ("spotbugs", "gradle-groovy", "spotbugs"),
            ("spotbugs", "maven", "spotbugs"),
            ("spring-modulith", "gradle-kotlin", "spring-modulith"),
            ("spring-modulith", "gradle-groovy", "spring-modulith"),
            ("spring-modulith", "maven", "spring-modulith"),
        ],
    )
    def test_all_snippet_table_cells_are_populated(
        self, tmp_path, tool, build_system, marker
    ):
        if build_system == "gradle-kotlin":
            (tmp_path / "build.gradle.kts").write_text("")
        elif build_system == "gradle-groovy":
            (tmp_path / "build.gradle").write_text("")
        elif build_system == "maven":
            (tmp_path / "pom.xml").write_text("<project/>")
        advice = advice_for(tool, tmp_path, reason=ABSENT)
        assert advice is not None, f"{tool} on {build_system} should have advice"
        assert (
            marker in advice.snippet
        ), f"{tool} on {build_system} should contain '{marker}' in snippet"


class TestNoInventedVersions:
    @pytest.mark.parametrize(
        "tool,build_system",
        [
            ("archunit", "gradle-kotlin"),
            ("archunit", "gradle-groovy"),
            ("archunit", "maven"),
            ("pit", "gradle-kotlin"),
            ("pit", "gradle-groovy"),
            ("pit", "maven"),
            ("jacoco", "gradle-kotlin"),
            ("jacoco", "gradle-groovy"),
            ("jacoco", "maven"),
            ("checkstyle", "gradle-kotlin"),
            ("checkstyle", "gradle-groovy"),
            ("checkstyle", "maven"),
            ("pmd", "gradle-kotlin"),
            ("pmd", "gradle-groovy"),
            ("pmd", "maven"),
            ("spotbugs", "gradle-kotlin"),
            ("spotbugs", "gradle-groovy"),
            ("spotbugs", "maven"),
            ("spring-modulith", "gradle-kotlin"),
            ("spring-modulith", "gradle-groovy"),
            ("spring-modulith", "maven"),
        ],
    )
    def test_no_advice_contains_a_version_literal(self, tmp_path, tool, build_system):
        if build_system == "gradle-kotlin":
            (tmp_path / "build.gradle.kts").write_text("")
        elif build_system == "gradle-groovy":
            (tmp_path / "build.gradle").write_text("")
        elif build_system == "maven":
            (tmp_path / "pom.xml").write_text("<project/>")
        advice = advice_for(tool, tmp_path, reason=ABSENT)
        assert advice is not None, f"{tool} on {build_system} should have advice"
        assert not re.search(
            r"\d+\.\d+", advice.snippet
        ), f"{tool} advice appears to pin a version: {advice.snippet}"


class TestInstallVersusUpgrade:
    def test_absent_advises_adding_it(self, tmp_path):
        (tmp_path / "build.gradle.kts").write_text("")
        advice = advice_for("pit", tmp_path, reason=ABSENT)
        assert advice.action == "add"

    def test_too_old_advises_upgrading_not_adding(self, tmp_path):
        (tmp_path / "build.gradle.kts").write_text("")
        advice = advice_for("pit", tmp_path, reason=TOO_OLD)
        assert advice.action == "upgrade"
        assert "class-file 69" in advice.note


class TestSilenceRatherThanGuessing:
    def test_an_unknown_build_system_yields_no_advice(self, tmp_path):
        assert advice_for("pit", tmp_path, reason=ABSENT) is None

    def test_an_unknown_tool_yields_no_advice(self, tmp_path):
        (tmp_path / "build.gradle.kts").write_text("")
        assert advice_for("nosuchtool", tmp_path, reason=ABSENT) is None

    def test_a_jdk_bundled_tool_needs_no_advice(self, tmp_path):
        (tmp_path / "build.gradle.kts").write_text("")
        assert advice_for("jdeps", tmp_path, reason=ABSENT) is None
