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
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Thresholds:
    cyclomatic_complexity: int | None
    source: str


NO_THRESHOLDS = Thresholds(cyclomatic_complexity=None, source="none declared")


class CheckstyleThresholds:
    """Read complexity thresholds from Checkstyle XML config files.

    Parses XML to find the CyclomaticComplexity module (which may be
    self-closing or have child properties) and extracts its 'max' property.
    The module may be top-level or nested inside a TreeWalker module.
    """

    def thresholds_for(self, repo_root):
        repo_root_path = Path(repo_root)
        config_candidates = [
            repo_root_path / "checkstyle.xml",
            repo_root_path / "config" / "checkstyle" / "checkstyle.xml",
        ]

        for config_path in config_candidates:
            if not config_path.exists():
                continue
            try:
                result = self._extract_from_xml(config_path)
                if result is not None:
                    return Thresholds(
                        cyclomatic_complexity=result,
                        source=str(config_path.relative_to(repo_root_path)),
                    )
            except (OSError, UnicodeDecodeError):
                continue
        return None

    def _extract_from_xml(self, config_path):
        """Extract CyclomaticComplexity max value from Checkstyle XML.

        Returns the max value as int, or None if not found or XML is malformed.
        Handles self-closing modules and TreeWalker nesting.
        """
        try:
            tree = ET.parse(config_path)
            root = tree.getroot()
        except ET.ParseError:
            return None

        # Find CyclomaticComplexity module: could be top-level or nested
        for module_elem in root.iter("module"):
            if module_elem.get("name") == "CyclomaticComplexity":
                # Look for property element with name="max"
                for prop_elem in module_elem.findall("property"):
                    if prop_elem.get("name") == "max":
                        try:
                            return int(prop_elem.get("value", ""))
                        except (TypeError, ValueError):
                            return None
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
    """Read complexity thresholds from ESLint config files.

    Tries flat config (ESLint 9+) first, then falls back to legacy .json format.
    Flat config extraction matches patterns like `complexity: ["error", N]` or
    `complexity: ["warn", N]` where N is a bare number. Strings and comments are
    excluded by sanitization. Does NOT extract: variables, object form
    ({ max: 10 }), spreads, or template expressions. Multiple conflicting
    candidates return None rather than guess.
    """

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

        Single-pass sanitization replaces strings and comments with spaces,
        preserving line structure and offsets. Then regex matches patterns
        that occur in code, never in blanked-out content.
        """
        if not config_path.exists():
            return None
        try:
            content = config_path.read_text()
        except (OSError, UnicodeDecodeError):
            return None

        # Sanitize: replace strings and comments with spaces, preserve newlines
        sanitized = self._sanitize_for_pattern_match(content)

        # Find all candidate patterns: complexity: [..., N]
        # After sanitization, strings are blanked, so pattern tolerates blanks
        # where the severity used to be: complexity: [   , 10] vs [error, 10]
        pattern = r"complexity\s*:\s*\[\s*[^,]*,\s*(\d+)\s*\]"
        candidates = []
        for match in re.finditer(pattern, sanitized):
            try:
                value = int(match.group(1))
                candidates.append(value)
            except (TypeError, ValueError):
                continue

        # No candidates, or conflicting candidates → return None (be conservative)
        if not candidates:
            return None
        if len(set(candidates)) > 1:
            return None

        # Exactly one value found
        try:
            return Thresholds(
                cyclomatic_complexity=candidates[0],
                source=config_path.name,
            )
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _sanitize_for_pattern_match(text):
        """Replace strings and comments with spaces, preserving line structure.

        Returns text of same length where:
        - Characters inside strings (', ", `) become spaces
        - Characters inside comments (// and /* */) become spaces
        - Newlines are always preserved
        - All other characters remain

        This allows regex patterns to safely match code-level constructs
        while avoiding false matches in strings or comments (e.g., URLs,
        documentation strings).
        """
        result = []
        i = 0
        while i < len(text):
            # Check for block comment start: /* ... */
            if i < len(text) - 1 and text[i : i + 2] == "/*":
                result.append(" ")
                result.append(" ")
                i += 2
                # Consume until end of block comment
                while i < len(text):
                    if i < len(text) - 1 and text[i : i + 2] == "*/":
                        result.append(" ")
                        result.append(" ")
                        i += 2
                        break
                    result.append("\n" if text[i] == "\n" else " ")
                    i += 1
                continue

            # Check for line comment start: // ...
            if i < len(text) - 1 and text[i : i + 2] == "//":
                result.append(" ")
                result.append(" ")
                i += 2
                # Consume until end of line
                while i < len(text) and text[i] != "\n":
                    result.append(" ")
                    i += 1
                # Preserve newline if present
                if i < len(text) and text[i] == "\n":
                    result.append("\n")
                    i += 1
                continue

            # Check for string literal start: ', ", or `
            if text[i] in ('"', "'", "`"):
                quote = text[i]
                result.append(" ")  # Opening quote becomes space
                i += 1
                # Consume string content until closing quote
                while i < len(text):
                    if text[i] == "\\" and i + 1 < len(text):
                        # Escape sequence: both chars become spaces
                        result.append(" ")
                        result.append(" ")
                        i += 2
                    elif text[i] == quote:
                        # Closing quote
                        result.append(" ")
                        i += 1
                        break
                    elif text[i] == "\n":
                        # Newline in string (valid in backticks)
                        result.append("\n")
                        i += 1
                    else:
                        result.append(" ")
                        i += 1
                continue

            # Regular character: copy as-is
            result.append(text[i])
            i += 1

        return "".join(result)


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
