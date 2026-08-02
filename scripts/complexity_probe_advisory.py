"""What a build needs to supply a tool that is missing.

Its own module because build coordinates and JDK-compatibility floors move on
someone else's release schedule; none of that should reach the probe, the sink
or the gate.

No version numbers live here on purpose. Every bytecode-reading tool must be
new enough to parse class-file 69 (Java 25), and a number written into source
goes stale silently — so the advice states the constraint and leaves the pin to
the reader.
"""

from dataclasses import dataclass
from pathlib import Path

ABSENT = "absent"
TOO_OLD = "too-old"

GRADLE_KOTLIN = "gradle-kotlin"
GRADLE_GROOVY = "gradle-groovy"
MAVEN = "maven"
UNKNOWN = "unknown"

_CLASS_FILE_NOTE = (
    "Must be new enough to read class-file 69 (Java 25); pin the current "
    "release rather than an older known-good version."
)

# tool -> build system -> snippet. A tool absent from this table gets no
# advice, which is the correct answer for jdeps (JDK-bundled) and lizard
# (a source-reading Python tool, never a build dependency).
_SNIPPETS = {
    "archunit": {
        GRADLE_KOTLIN: 'testImplementation("com.tngtech.archunit:archunit-junit5:<version>")',
        GRADLE_GROOVY: "testImplementation 'com.tngtech.archunit:archunit-junit5:<version>'",
        MAVEN: "<dependency> com.tngtech.archunit:archunit-junit5, <scope>test</scope>",
    },
    "pit": {
        GRADLE_KOTLIN: 'id("info.solidsoft.pitest") + testImplementation("org.pitest:pitest-junit5-plugin:<version>")',
        GRADLE_GROOVY: "id 'info.solidsoft.pitest' + testImplementation 'org.pitest:pitest-junit5-plugin:<version>'",
        MAVEN: "<plugin> org.pitest:pitest-maven, with org.pitest:pitest-junit5-plugin as a plugin dependency",
    },
    "jacoco": {
        GRADLE_KOTLIN: "plugins { jacoco }  // built in to Gradle",
        GRADLE_GROOVY: "plugins { jacoco }  // built in to Gradle",
        MAVEN: "<plugin> org.jacoco:jacoco-maven-plugin",
    },
    "checkstyle": {
        GRADLE_KOTLIN: "plugins { checkstyle }  // built in to Gradle",
        GRADLE_GROOVY: "plugins { checkstyle }  // built in to Gradle",
        MAVEN: "<plugin> org.apache.maven.plugins:maven-checkstyle-plugin",
    },
    "pmd": {
        GRADLE_KOTLIN: "plugins { pmd }  // built in to Gradle",
        GRADLE_GROOVY: "plugins { pmd }  // built in to Gradle",
        MAVEN: "<plugin> org.apache.maven.plugins:maven-pmd-plugin",
    },
    "spotbugs": {
        GRADLE_KOTLIN: 'id("com.github.spotbugs")',
        GRADLE_GROOVY: "id 'com.github.spotbugs'",
        MAVEN: "<plugin> com.github.spotbugs:spotbugs-maven-plugin",
    },
    "spring-modulith": {
        GRADLE_KOTLIN: 'testImplementation("org.springframework.modulith:spring-modulith-starter-test")  // version from the Boot BOM',
        GRADLE_GROOVY: "testImplementation 'org.springframework.modulith:spring-modulith-starter-test'  // version from the Boot BOM",
        MAVEN: "<dependency> org.springframework.modulith:spring-modulith-starter-test, version from the Boot BOM",
    },
}

# Tools that read bytecode, and so carry the class-file 69 caveat.
_BYTECODE_TOOLS = ("archunit", "pit", "jacoco", "spotbugs")


@dataclass(frozen=True)
class Advice:
    tool: str
    action: str
    snippet: str
    note: str


def detect_build_system(repo_root) -> str:
    root = Path(repo_root)
    if (root / "build.gradle.kts").exists():
        return GRADLE_KOTLIN
    if (root / "build.gradle").exists():
        return GRADLE_GROOVY
    if (root / "pom.xml").exists():
        return MAVEN
    return UNKNOWN


def advice_for(tool, repo_root, reason=ABSENT, build_system=None):
    """None means "nothing useful to say" — never a guess."""
    system = build_system or detect_build_system(repo_root)
    if system == UNKNOWN:
        return None
    snippet = _SNIPPETS.get(tool, {}).get(system)
    if snippet is None:
        return None
    note = _CLASS_FILE_NOTE if tool in _BYTECODE_TOOLS else ""
    action = "upgrade" if reason == TOO_OLD else "add"
    return Advice(tool=tool, action=action, snippet=snippet, note=note)
