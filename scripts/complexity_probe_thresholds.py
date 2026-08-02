"""Where a project's declared complexity limits are read from.

Separate because this changes when a *build tool* changes its config format —
nothing to do with how code is measured or how a verdict is reached. Adding a
tool is adding a class and one registry entry; `discover_thresholds` never
needs editing.

The plugin ships no numbers. A repo that declares no limit gets no limit, which
is what keeps docs/clean-code-standard.md's rejection of universal numbers
intact rather than quietly contradicted.
"""

import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Thresholds:
    cyclomatic_complexity: int | None
    source: str


NO_THRESHOLDS = Thresholds(cyclomatic_complexity=None, source="none declared")

_CHECKSTYLE_COMPLEXITY = re.compile(
    r'<module\s+name="CyclomaticComplexity".*?'
    r'<property\s+name="max"\s+value="(?P<max>\d+)"',
    re.DOTALL,
)


class CheckstyleThresholds:
    def thresholds_for(self, repo_root):
        config_path = Path(repo_root) / "checkstyle.xml"
        if not config_path.exists():
            return None
        match = _CHECKSTYLE_COMPLEXITY.search(config_path.read_text())
        if not match:
            return None
        return Thresholds(
            cyclomatic_complexity=int(match.group("max")), source="checkstyle.xml"
        )


class PmdThresholds:
    def thresholds_for(self, repo_root):
        config_path = Path(repo_root) / "pmd-ruleset.xml"
        if not config_path.exists():
            return None
        match = re.search(
            r'<property\s+name="(?:classReportLevel|methodReportLevel)"\s+'
            r'value="(?P<max>\d+)"',
            config_path.read_text(),
        )
        if not match:
            return None
        return Thresholds(
            cyclomatic_complexity=int(match.group("max")), source="pmd-ruleset.xml"
        )


class RuffThresholds:
    def thresholds_for(self, repo_root):
        config_path = Path(repo_root) / "pyproject.toml"
        if not config_path.exists():
            return None
        try:
            parsed = tomllib.loads(config_path.read_text())
        except tomllib.TOMLDecodeError:
            return None
        mccabe = (
            parsed.get("tool", {}).get("ruff", {}).get("lint", {}).get("mccabe", {})
        )
        maximum = mccabe.get("max-complexity")
        if maximum is None:
            return None
        return Thresholds(
            cyclomatic_complexity=int(maximum),
            source="pyproject.toml [tool.ruff.lint.mccabe]",
        )


class EslintThresholds:
    def thresholds_for(self, repo_root):
        config_path = Path(repo_root) / ".eslintrc.json"
        if not config_path.exists():
            return None
        try:
            parsed = json.loads(config_path.read_text())
        except json.JSONDecodeError:
            return None
        rule = parsed.get("rules", {}).get("complexity")
        if isinstance(rule, list) and len(rule) > 1:
            try:
                return Thresholds(
                    cyclomatic_complexity=int(rule[1]), source=".eslintrc.json"
                )
            except TypeError, ValueError:
                return None
        return None


class NullThresholds:
    """The honest default: this project declares nothing."""

    def thresholds_for(self, repo_root):
        return None


def default_threshold_sources():
    """The sources a normal run consults, in order."""
    return (
        CheckstyleThresholds(),
        PmdThresholds(),
        RuffThresholds(),
        EslintThresholds(),
    )


def discover_thresholds(repo_root, sources=None) -> Thresholds:
    for source in sources if sources is not None else default_threshold_sources():
        thresholds = source.thresholds_for(repo_root)
        if thresholds is not None:
            return thresholds
    return NO_THRESHOLDS
