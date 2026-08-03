"""Where a project's declared complexity limits are read from.

Separate because this changes when a *build tool* changes its config format —
nothing to do with how code is measured or how a verdict is reached. Adding a
tool is adding a class and one registry entry; `discover_thresholds` never
needs editing.

The plugin ships no numbers. A repo that declares no limit gets no limit, which
is what keeps docs/clean-code-standard.md's rejection of universal numbers
intact rather than quietly contradicted.

Every source here reads a file some *other* tool owns, so every source treats a
file it cannot read or cannot understand as absence: a missing permission, a
truncated config or a typo'd value returns `None`, never an exception. A repo
with a typo in its ruff config is owed a measurement and a stated limit of
"none", not a traceback.
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


def no_thresholds_because(reason: str) -> Thresholds:
    """Absent thresholds that say why nothing could be read.

    `NO_THRESHOLDS` means "this repo declares no limit", which is a finding.
    This means "discovery could not answer", which is a different fact, and
    absence without a cause is the silence this design exists to catch.
    """
    return Thresholds(cyclomatic_complexity=None, source=f"none readable — {reason}")


def _local_name(tag: str) -> str:
    """An element's name with any XML namespace stripped.

    PMD rulesets normally declare a default namespace, which ElementTree folds
    into every tag as `{uri}name`. Matching on the local name reads a
    namespaced and a bare ruleset identically.
    """
    return tag.rpartition("}")[2]


def _nested_table_value(parsed, table_path, key):
    """The value at `key` inside the nested table `table_path`, else None.

    Any hop that is missing, or that turns out not to be a table, means the
    config does not declare this key. A config whose shape surprises us
    declares nothing — it never raises.
    """
    current = parsed
    for table_name in table_path:
        if not isinstance(current, dict):
            return None
        current = current.get(table_name)
    if not isinstance(current, dict):
        return None
    return current.get(key)


# ESLint severities that turn a rule off. A number written beside one of these
# is not a declared limit: the repo asked for the rule not to run at all.
_DISABLED_SEVERITY_TOKENS = frozenset(("off", '"off"', "'off'", "0"))


def _severity_disables_the_rule(severity_token: str) -> bool:
    """Whether an ESLint severity token, as written, turns the rule off.

    Takes the token as text so the flat-config path (which only ever has the
    source text) and the legacy JSON path (which has a parsed value) can share
    one predicate. They have always agreed on what a severity means and must
    keep agreeing.
    """
    return severity_token.strip() in _DISABLED_SEVERITY_TOKENS


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
            except OSError, UnicodeDecodeError:
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
                        except TypeError, ValueError:
                            return None
        return None


class PmdThresholds:
    """Read complexity thresholds from PMD ruleset files.

    PMD has no standard location for rulesets — they are always configured
    explicitly. This checks `pmd-ruleset.xml` as a common convention.

    Parsed as XML rather than matched textually, for the same reason
    `CheckstyleThresholds` is: a property has to be read from the rule element
    that owns it. PMD's `CyclomaticComplexity` declares two limits,
    `classReportLevel` and `methodReportLevel`, and the class-level one
    conventionally comes first — so the first textual match in the file is
    usually the wrong number by a wide margin.

    Only `methodReportLevel` is read. This probe measures functions, so a
    per-class limit is not a limit a function can breach; comparing against it
    silently disables the "worth a look" marker for every PMD repo. A ruleset
    declaring only `classReportLevel` therefore declares no per-function limit,
    and gets `None` — a wrong number costs more than an absent one.
    """

    _CYCLOMATIC_RULE = "CyclomaticComplexity"
    _METHOD_REPORT_LEVEL = "methodReportLevel"

    def thresholds_for(self, repo_root):
        config_path = Path(repo_root) / "pmd-ruleset.xml"
        if not config_path.exists():
            return None
        try:
            root = ET.parse(config_path).getroot()
        except OSError, UnicodeDecodeError, ET.ParseError:
            return None

        for rule_element in root.iter():
            if _local_name(rule_element.tag) != "rule":
                continue
            if not self._is_cyclomatic_complexity_rule(rule_element):
                continue
            declared = self._method_report_level(rule_element)
            if declared is not None:
                return Thresholds(
                    cyclomatic_complexity=declared, source="pmd-ruleset.xml"
                )
        return None

    @classmethod
    def _is_cyclomatic_complexity_rule(cls, rule_element) -> bool:
        """Whether this `<rule>` configures PMD's CyclomaticComplexity.

        A rule names itself either by `ref` (the usual
        `category/java/design.xml/CyclomaticComplexity`) or by `name` when
        defined inline.
        """
        reference = rule_element.get("ref", "")
        name = rule_element.get("name", "")
        return cls._CYCLOMATIC_RULE in reference or cls._CYCLOMATIC_RULE in name

    @classmethod
    def _method_report_level(cls, rule_element):
        """This rule's own `methodReportLevel`, as an int, or None."""
        for property_element in rule_element.iter():
            if _local_name(property_element.tag) != "property":
                continue
            if property_element.get("name") != cls._METHOD_REPORT_LEVEL:
                continue
            try:
                return int(property_element.get("value", ""))
            except TypeError, ValueError:
                return None
        return None


class RuffThresholds:
    # The current table first, then the still-functional deprecated one.
    _MCCABE_TABLES = (
        (("tool", "ruff", "lint", "mccabe"), "pyproject.toml [tool.ruff.lint.mccabe]"),
        (("tool", "ruff", "mccabe"), "pyproject.toml [tool.ruff.mccabe] (deprecated)"),
    )

    def thresholds_for(self, repo_root):
        config_path = Path(repo_root) / "pyproject.toml"
        if not config_path.exists():
            return None
        try:
            parsed = tomllib.loads(config_path.read_text())
        except OSError, UnicodeDecodeError, tomllib.TOMLDecodeError:
            # Unreadable (permissions, encoding) or malformed TOML: this repo
            # declares nothing we can read. Absence, never a crash.
            return None

        for table_path, source in self._MCCABE_TABLES:
            declared = _nested_table_value(parsed, table_path, "max-complexity")
            if declared is None:
                continue
            try:
                return Thresholds(cyclomatic_complexity=int(declared), source=source)
            except TypeError, ValueError:
                # `max-complexity = "ten"`. The table declares something, but
                # not a limit; keep looking rather than crash the whole run.
                continue

        return None


class EslintThresholds:
    """Read complexity thresholds from ESLint config files.

    Tries flat config (ESLint 9+) first, then falls back to legacy .json format.

    Flat config is JavaScript, and this module is not a JavaScript parser. It
    extracts only the one shape it can be certain about: `complexity` set to an
    array whose severity is a *literal* — `"error"`, `"warn"`, `"off"` (either
    quote style) or the numeric form `0`, `1`, `2` — and whose second element is
    a bare integer. A severity that turns the rule *off* (`"off"` or `0`) yields
    no limit on either path: a rule the repo explicitly disabled declares
    nothing, whatever number is still written beside it.

    Everything else is absence, because a wrong number costs
    more than a missing one. Deliberately NOT extracted: variable severities
    (`[level, 10]`), spreads (`[...base, 10]`), calls (`[sev(), 10]`), template
    literals (`` [`error`, 10] ``), and the object form (`["error", {max: 10}]`).
    Matches inside strings and comments are excluded by sanitization, and two
    surviving candidates that disagree yield None rather than a guess.
    """

    # Run against sanitized text, where strings and comments are blank. Any
    # comma, bracket or digit the pattern sees is therefore real code. The
    # severity slot is captured but not judged here: sanitization has already
    # blanked a literal severity, so the original text at the same offsets is
    # what says whether it was a literal or live code.
    _FLAT_COMPLEXITY_RULE = re.compile(
        r"complexity\s*:\s*\[(?P<severity>[^,\]]*),\s*(?P<max>\d+)\s*\]"
    )

    # The severity slot as it reads in the *original* source. Only ESLint's
    # literal severity vocabulary counts; an identifier, spread, call or
    # template literal in this slot means the array cannot be read statically.
    _LITERAL_SEVERITY = re.compile(
        r"""\A\s*(?:"(?:error|warn|off)"|'(?:error|warn|off)'|[012])\s*\Z"""
    )

    # A `/` after one of these begins a regex literal; after anything else
    # (an identifier, a number, `)`, `]`, a string) it is division. This is a
    # heuristic, not a JavaScript grammar: it is the standard last-significant-
    # token rule and it is wrong for the rare keyword operands it does not know
    # (`typeof /re/`, `case /re/:`). Both mistakes cost at most a missed
    # threshold, never an invented one.
    #
    # `>` is in the set because it closes an arrow (`=>`) as well as a
    # comparison, and in both positions a following `/` opens a regex rather
    # than divides. Arrow functions are near-universal in eslint.config.js, so
    # omitting it lost the real rule in the common case.
    _REGEX_LITERAL_PRECEDERS = frozenset("(,=:[!&|?{};>")

    # The one keyword operand common enough to be worth knowing.
    _REGEX_LITERAL_KEYWORD = "return"

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
        except OSError, UnicodeDecodeError, json.JSONDecodeError:
            # Unreadable or not JSON: absence, never a crash.
            return None

        # A JSON document whose root is anything but an object (`[1,2,3]`, a
        # bare string) is not an ESLint config. Asking it for `rules` used to
        # be an AttributeError escaping all the way to the user.
        rules = parsed.get("rules") if isinstance(parsed, dict) else None
        rule = rules.get("complexity") if isinstance(rules, dict) else None
        if not isinstance(rule, list) or len(rule) < 2:
            return None
        if _severity_disables_the_rule(str(rule[0])):
            return None
        try:
            return Thresholds(
                cyclomatic_complexity=int(rule[1]), source=".eslintrc.json"
            )
        except TypeError, ValueError:
            return None

    def _extract_from_flat_config(self, config_path):
        """Extract complexity limit from flat config JS file.

        Sanitization blanks strings, comments and regex literals in a single
        left-to-right pass, preserving length so offsets still address the
        original source. The rule pattern then runs on the sanitized copy —
        where every comma, bracket and digit it sees is real code — and each
        candidate's severity slot is judged on the *original* text, which is
        the only place a literal severity is still distinguishable from a
        variable, a spread or a template literal.
        """
        if not config_path.exists():
            return None
        try:
            content = config_path.read_text()
        except OSError, UnicodeDecodeError:
            return None

        sanitized = self._sanitize_for_pattern_match(content)
        # The severity slot below is read out of the ORIGINAL text using a span
        # found in the sanitized copy. That is only sound while sanitization is
        # length-preserving. Fuzzing confirms it holds; nothing else says it
        # must, so say it here where the dependency actually lives.
        assert len(sanitized) == len(content), (
            "sanitization must preserve length: the severity slot is read from "
            "the original text by offsets found in the sanitized copy"
        )

        declared_maximums = set()
        for match in self._FLAT_COMPLEXITY_RULE.finditer(sanitized):
            severity_start, severity_end = match.span("severity")
            severity_as_written = content[severity_start:severity_end]
            if not self._LITERAL_SEVERITY.match(severity_as_written):
                continue
            if _severity_disables_the_rule(severity_as_written):
                continue
            declared_maximums.add(int(match.group("max")))

        # Nothing readable, or readable candidates that disagree: the config
        # does not confidently declare one number, so it declares none.
        if len(declared_maximums) != 1:
            return None

        return Thresholds(
            cyclomatic_complexity=declared_maximums.pop(),
            source=config_path.name,
        )

    @staticmethod
    def _blank_preserving_newlines(segment):
        """Return `segment` with every character but newlines turned to spaces.

        Same length in, same length out: that is what lets a match on the
        sanitized copy address the original source by offset.
        """
        return "".join("\n" if character == "\n" else " " for character in segment)

    @classmethod
    def _scan_block_comment(cls, text, start):
        """Blank `/* ... */` from `start`. Returns (blanked, index after it)."""
        closing = text.find("*/", start + 2)
        end = len(text) if closing == -1 else closing + 2
        return cls._blank_preserving_newlines(text[start:end]), end

    @classmethod
    def _scan_line_comment(cls, text, start):
        """Blank `// ...` up to (not including) the newline that ends it."""
        newline = text.find("\n", start)
        end = len(text) if newline == -1 else newline
        return cls._blank_preserving_newlines(text[start:end]), end

    @classmethod
    def _scan_string_literal(cls, text, start):
        """Blank a `'`, `"` or backtick literal, quotes included.

        Backslash escapes do not end the literal. An unterminated literal is
        blanked to end of input, which is absence rather than a crash.
        """
        quote = text[start]
        index = start + 1
        while index < len(text):
            if text[index] == "\\" and index + 1 < len(text):
                index += 2
            elif text[index] == quote:
                index += 1
                break
            else:
                index += 1
        return cls._blank_preserving_newlines(text[start:index]), index

    @classmethod
    def _scan_regex_literal(cls, text, start):
        """Blank a `/.../` literal, delimiters included.

        A `/` inside a character class does not close the literal — that is
        what makes `/["']/` safe to blank rather than read as a stray quote.
        A regex literal cannot span lines, so an unterminated one is blanked
        only to the end of its line; the following lines stay code.
        """
        index = start + 1
        inside_character_class = False
        while index < len(text):
            character = text[index]
            if character == "\\" and index + 1 < len(text):
                index += 2
                continue
            if character == "\n":
                break
            if character == "[":
                inside_character_class = True
            elif character == "]":
                inside_character_class = False
            elif character == "/" and not inside_character_class:
                index += 1
                break
            index += 1
        return cls._blank_preserving_newlines(text[start:index]), index

    @staticmethod
    def _preceding_word(text, index):
        """The identifier ending just before `index`, ignoring whitespace."""
        end = index
        while end > 0 and text[end - 1].isspace():
            end -= 1
        start = end
        while start > 0 and (text[start - 1].isalnum() or text[start - 1] == "_"):
            start -= 1
        return text[start:end]

    @classmethod
    def _begins_regex_literal(cls, text, index, last_significant_character):
        """Whether the `/` at `index` opens a regex literal rather than divides.

        Judged from the last significant character, as a real tokenizer would:
        after a value (identifier, number, `)`, `]`, a string) a `/` divides;
        after an operator or an opening bracket it begins a regex.
        """
        if last_significant_character is None:
            return True
        if last_significant_character in cls._REGEX_LITERAL_PRECEDERS:
            return True
        return cls._preceding_word(text, index) == cls._REGEX_LITERAL_KEYWORD

    @classmethod
    def _sanitize_for_pattern_match(cls, text):
        """Blank strings, comments and regex literals in one left-to-right pass.

        Returns text of the same length, with newlines preserved, where every
        character that belonged to a string, a comment or a regex literal is a
        space and all other characters are untouched. One pass is the whole
        point: a two-pass version cannot tell a `//` inside a URL string from a
        comment, because whichever pass runs first has to guess.
        """
        sanitized = []
        index = 0
        last_significant_character = None

        while index < len(text):
            character = text[index]
            next_two_characters = text[index : index + 2]

            if next_two_characters == "/*":
                blanked, index = cls._scan_block_comment(text, index)
                sanitized.append(blanked)
                continue

            if next_two_characters == "//":
                blanked, index = cls._scan_line_comment(text, index)
                sanitized.append(blanked)
                continue

            if character in ('"', "'", "`"):
                blanked, index = cls._scan_string_literal(text, index)
                sanitized.append(blanked)
                # A string is a value, so a `/` after it means division.
                last_significant_character = character
                continue

            if character == "/" and cls._begins_regex_literal(
                text, index, last_significant_character
            ):
                blanked, index = cls._scan_regex_literal(text, index)
                sanitized.append(blanked)
                # A regex literal is a value too.
                last_significant_character = "/"
                continue

            sanitized.append(character)
            if not character.isspace():
                last_significant_character = character
            index += 1

        return "".join(sanitized)


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
