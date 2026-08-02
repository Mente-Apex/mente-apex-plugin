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

_CHECKSTYLE_COMPLEXITY_MODULE = re.compile(
    r'<module\s+name="CyclomaticComplexity".*?</module>', re.DOTALL
)

_MAX_PROPERTY = re.compile(r'<property\s+name="max"\s+value="(?P<max>\d+)"')


class CheckstyleThresholds:
    def thresholds_for(self, repo_root):
        repo_root_path = Path(repo_root)
        config_candidates = [
            repo_root_path / "checkstyle.xml",
            repo_root_path / "config" / "checkstyle" / "checkstyle.xml",
        ]

        for config_path in config_candidates:
            if not config_path.exists():
                continue
            content = config_path.read_text()
            module_match = _CHECKSTYLE_COMPLEXITY_MODULE.search(content)
            if not module_match:
                continue
            property_match = _MAX_PROPERTY.search(module_match.group(0))
            if not property_match:
                continue
            return Thresholds(
                cyclomatic_complexity=int(property_match.group("max")),
                source=str(config_path.relative_to(repo_root_path)),
            )
        return None


class PmdThresholds:
    """Read complexity thresholds from PMD ruleset files.

    PMD has no standard location for rulesets — they are always configured
    explicitly. This checks `pmd-ruleset.xml` as a common convention.
    Matches properties named classReportLevel or methodReportLevel.
    """

    _PMD_PROPERTY = re.compile(
        r'<property\s+name="(?:classReportLevel|methodReportLevel)"\s+'
        r'value="(?P<max>\d+)"'
    )

    def thresholds_for(self, repo_root):
        config_path = Path(repo_root) / "pmd-ruleset.xml"
        if not config_path.exists():
            return None
        try:
            content = config_path.read_text()
        except (OSError, UnicodeDecodeError):
            return None
        match = self._PMD_PROPERTY.search(content)
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

        # Try current location first: tool.ruff.lint.mccabe
        mccabe = (
            parsed.get("tool", {}).get("ruff", {}).get("lint", {}).get("mccabe", {})
        )
        maximum = mccabe.get("max-complexity")
        if maximum is not None:
            return Thresholds(
                cyclomatic_complexity=int(maximum),
                source="pyproject.toml [tool.ruff.lint.mccabe]",
            )

        # Fall back to deprecated location: tool.ruff.mccabe
        mccabe_legacy = parsed.get("tool", {}).get("ruff", {}).get("mccabe", {})
        maximum_legacy = mccabe_legacy.get("max-complexity")
        if maximum_legacy is not None:
            return Thresholds(
                cyclomatic_complexity=int(maximum_legacy),
                source="pyproject.toml [tool.ruff.mccabe] (deprecated)",
            )

        return None


class EslintThresholds:
    def thresholds_for(self, repo_root):
        repo_root_path = Path(repo_root)

        # Try flat config first (ESLint 9+): eslint.config.js or eslint.config.mjs
        flat_config_candidates = [
            repo_root_path / "eslint.config.js",
            repo_root_path / "eslint.config.mjs",
        ]
        for flat_config_path in flat_config_candidates:
            result = self._extract_from_flat_config(flat_config_path)
            if result is not None:
                return result

        # Fall back to legacy format: .eslintrc.json
        legacy_config_path = repo_root_path / ".eslintrc.json"
        if not legacy_config_path.exists():
            return None
        try:
            parsed = json.loads(legacy_config_path.read_text())
        except json.JSONDecodeError:
            return None
        rule = parsed.get("rules", {}).get("complexity")
        if isinstance(rule, list) and len(rule) > 1:
            try:
                return Thresholds(
                    cyclomatic_complexity=int(rule[1]), source=".eslintrc.json"
                )
            except (TypeError, ValueError):
                return None
        return None

    def _extract_from_flat_config(self, config_path):
        """Extract complexity limit from flat config JS file.

        Flat config is a JavaScript module. We use conservative regex matching:
        looking for a pattern like `rules: { complexity: ["error", N] }`.
        If the pattern cannot be confidently matched, return None rather than
        guess — a wrong number is far worse than "none declared".
        """
        if not config_path.exists():
            return None
        try:
            content = config_path.read_text()
        except (OSError, UnicodeDecodeError):
            return None

        # Match patterns like: complexity: ["error", 10] or complexity: ["warn", 10]
        # Also handle: complexity: ["error", { max: 10 }] (less common)
        match = re.search(
            r'complexity\s*:\s*\[\s*["\'](?:error|warn)["\'],\s*(\d+)\s*\]', content
        )
        if match:
            try:
                return Thresholds(
                    cyclomatic_complexity=int(match.group(1)),
                    source=config_path.name,
                )
            except (TypeError, ValueError):
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
