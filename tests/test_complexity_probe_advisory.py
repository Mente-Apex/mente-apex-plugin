"""Advice makes `unverified` actionable. It never blocks, never invents a
version, and distinguishes install from upgrade."""

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


class TestNoInventedVersions:
    def test_no_advice_contains_a_version_literal(self, tmp_path):
        (tmp_path / "build.gradle.kts").write_text("")
        for tool in ("archunit", "pit", "jacoco", "checkstyle", "pmd"):
            advice = advice_for(tool, tmp_path, reason=ABSENT)
            assert not any(
                part.replace(".", "").isdigit() and "." in part
                for part in advice.snippet.split('"')
            ), f"{tool} advice appears to pin a version"


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
