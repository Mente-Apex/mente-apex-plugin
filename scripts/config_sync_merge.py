"""
config_sync_merge.py — the text/JSON merge engine for config sync.

A closed, side-effect-free algorithm extracted out of config_sync.py (SRP): it
folds two snapshots' {path: content} maps into one, deep-merging JSON, unioning
markdown by section, and emitting conflict markers only for genuine
key/value contradictions. Nothing here touches the filesystem, CLAUDE_DIR, or
any sync state — it takes strings in and returns strings out, so a merge bug is
read and fixed in one focused module instead of the 1000+-line engine.

Dependency direction is one-way: config_sync imports these helpers; this module
imports nothing from config_sync (keeping it free of the god-module and free of
import cycles).
"""

import json
import os
import re
import shutil
import subprocess

# Nested `claude -p` merges are OFF by default: /config-sync runs *inside* Claude
# Code, so shelling out spawns a nested Claude per differing file. Opt in with
# CONFIG_SYNC_LLM_MERGE=1, and even then cap invocations per run (the cap itself
# lives with cmd_consolidate, the command that spends the budget).
LLM_MERGE_ENV = "CONFIG_SYNC_LLM_MERGE"


def _merge_snapshot_files(files_base: dict, files_override: dict, budget=None) -> tuple:
    """Merge two snapshots' {path: content} maps into one.

    On conflict the override side wins (scalars), markdown unions by section,
    JSON deep-merges. Returns (merged_files, merge_log). This is the shared core
    used by both `cmd_merge` (pairwise CLI) and `cmd_consolidate` (timestamp fold).
    `budget` is an optional _LlmMergeBudget threaded into text merges.
    """
    all_keys = sorted(set(files_base) | set(files_override))
    merged_files = {}
    merge_log = []

    for key in all_keys:
        base_content = files_base.get(key)
        override_content = files_override.get(key)

        if base_content is None:
            merged_files[key] = override_content
            merge_log.append({"file": key, "strategy": "b-only"})
        elif override_content is None:
            merged_files[key] = base_content
            merge_log.append({"file": key, "strategy": "a-only"})
        elif base_content == override_content:
            merged_files[key] = base_content
            merge_log.append({"file": key, "strategy": "identical"})
        else:
            # JSON files (settings.json) need deep-merge, not text merge
            if key.endswith(".json"):
                merged, strategy = _deep_merge_json(base_content, override_content)
            else:
                merged, strategy = _smart_merge_text(
                    base_content, override_content, context=key, budget=budget
                )
            merged_files[key] = merged
            # Whether the union could actually reconcile the two sides is
            # recorded HERE, where it is known, rather than left for each
            # caller to re-derive by scanning content. An unreconciled
            # contradiction embeds conflict markers into a file that is about
            # to be written to the operator's live config, so it has to be
            # visible in the log the caller reports.
            entry = {"file": key, "strategy": strategy}
            # A conflict THIS fold introduced, not markers that were already
            # in the content. `cmd_consolidate` folds the previous consolidated
            # snapshot back in, so once markers existed anywhere they appeared
            # in every later merge's output -- and the conflict was reported
            # forever, including after both machines had pushed the resolved
            # file. Reporting a contradiction that no longer exists trains the
            # operator to ignore the one that does.
            if isinstance(merged, str) and CONFLICT_MARKER in merged:
                already_present = CONFLICT_MARKER in (base_content or "") or (
                    CONFLICT_MARKER in (override_content or "")
                )
                if not already_present:
                    entry["conflict"] = True
            merge_log.append(entry)

    return merged_files, merge_log


def _deep_merge_json(version_a: str, version_b: str) -> tuple:
    """
    Deep-merge two JSON strings (e.g. settings.json).
    version_b's scalar values win on conflict; lists are unioned; dicts recurse.
    Returns (merged_json_string, strategy_name).
    """

    def _merge(base, override):
        if isinstance(base, dict) and isinstance(override, dict):
            result = dict(base)
            for key, value in override.items():
                result[key] = _merge(base.get(key), value)
            return result
        if isinstance(base, list) and isinstance(override, list):
            # Union: keep all unique items (order: base first, then new from override)
            seen = []
            result = list(base)
            for item in base:
                try:
                    seen.append(json.dumps(item, sort_keys=True))
                except TypeError:
                    seen.append(str(item))
            for item in override:
                try:
                    key = json.dumps(item, sort_keys=True)
                except TypeError:
                    key = str(item)
                if key not in seen:
                    result.append(item)
                    seen.append(key)
            return result
        # Scalar: override wins (more recent machine's value)
        return override if override is not None else base

    try:
        obj_a = json.loads(version_a) if version_a else {}
        obj_b = json.loads(version_b) if version_b else {}
        merged = _merge(obj_a, obj_b)
        return json.dumps(merged, indent=2, ensure_ascii=False), "json-deep-merge"
    except json.JSONDecodeError:
        # If either side is corrupt JSON, fall back to keeping A
        return version_a, "json-fallback-kept-a"


class _LlmMergeBudget:
    """Caps how many nested `claude -p` merges a single run may spend.

    Injected into the merge fold so the cap is explicit state, not a hidden
    module global. `None` (the default) means "no cap object" — the env gate
    alone decides, appropriate for a single pairwise `merge`.
    """

    def __init__(self, limit: int):
        self.remaining = limit

    def try_consume(self) -> bool:
        if self.remaining <= 0:
            return False
        self.remaining -= 1
        return True


def _smart_merge_text(
    version_a: str,
    version_b: str,
    context: str = "",
    budget: _LlmMergeBudget | None = None,
) -> tuple:
    """
    Merge two text blobs. Returns (merged_text, strategy_name).

    Structured section-union is the default. The LLM path (`claude -p`) is only
    taken when explicitly opted in via CONFIG_SYNC_LLM_MERGE=1 and the injected
    budget still has room — this run executes *inside* Claude Code, so nesting a
    Claude per differing file is a cost/latency dead-end left off by default.
    """
    llm_enabled = os.environ.get(LLM_MERGE_ENV) == "1"
    if (
        llm_enabled
        and shutil.which("claude")
        and (budget is None or budget.try_consume())
    ):
        prompt = (
            f"Merge these two versions of '{context}' into one coherent document.\n"
            "Rules:\n"
            "- Remove exact duplicates\n"
            "- Resolve contradictions by keeping the more specific or detailed version\n"
            "- Preserve all unique content from both versions\n"
            "- Keep the same general structure and tone\n"
            "- Output ONLY the merged content, no explanation or commentary\n\n"
            f"=== VERSION A ===\n{version_a}\n\n"
            f"=== VERSION B ===\n{version_b}"
        )
        try:
            result = subprocess.run(
                ["claude", "-p", prompt], capture_output=True, text=True, timeout=90
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip(), "llm-merge"
        except subprocess.TimeoutExpired, FileNotFoundError:
            pass

    # Default / fallback: section-aware union
    return _section_union(version_a, version_b), "section-union"


# A conflict identity is only claimed for a line that really looks like a
# `key: value` assignment: a short label of word characters (spaces, hyphens,
# underscores and dots allowed inside it), then a colon, then whitespace or end
# of line.
#
# The old rule was `([^:]+):` -- anything at all up to the first colon. That
# made `see https://a.example` a line with key `https`, so two prose lines
# citing different URLs were declared a contradiction, and B's line was then
# REMOVED from the merged body (kept only inside the marker block). Ordinary
# prose (`Note: ...`, `Warning: ...`) collided the same way. A fabricated
# conflict is worse than a missed one here: a missed one unions both lines,
# a fabricated one drops content and demands the operator resolve a
# contradiction that does not exist.
_KEY_LINE = re.compile(r"^(?P<key>[A-Za-z0-9_][A-Za-z0-9 _.\-]{0,40}):(?:\s|$)")

# At most this many words in a key. "Default branch: main" is a real key;
# a sentence that happens to contain a colon is not.
_MAX_KEY_WORDS = 3


def _line_key(line: str):
    """Conflict identity of a line, or None if it can only be unioned.

    List items (-, *, +, `N.`) and blank lines never conflict — they union.
    Only `key: value` style lines carry an identity that can contradict, and
    only when they look like one: see `_KEY_LINE`. Returning None is always
    the safe answer, because it unions rather than fabricating a conflict.
    """
    stripped = line.strip()
    if not stripped or stripped[0] in "-*+" or re.match(r"\d+\.", stripped):
        return None
    match = _KEY_LINE.match(stripped)
    if match is None:
        return None
    key = match.group("key").strip()
    if len(key.split()) > _MAX_KEY_WORDS:
        return None
    return key


# The marker `_section_union` writes when two lines with the same key carry
# different values. One definition, so "did this merge conflict?" has a single
# answer rather than one spelling per caller.
CONFLICT_MARKER = "<<<<<<< Machine A"

_PREAMBLE = "__preamble__"

# A Markdown ATX heading: one to six `#` at the start of the line, then either
# whitespace or end of line. `line.startswith("#")` matched far more than that
# -- a `# install deps` comment inside a ```bash fence, a `#!/usr/bin/env`
# shebang, a C `#include`. Each one opened a bogus section boundary mid-code-
# block, and the merged output then emitted new lines AFTER the closing fence,
# silently breaking the snippet.
_HEADING = re.compile(r"^#{1,6}(\s|$)")
_FENCE = re.compile(r"^(`{3,}|~{3,})")


def _parse_sections(text: str):
    """Split `text` into `(key, heading, body)` triples in document order.

    A list of triples rather than a `{heading: body}` dict, because a document
    may legitimately repeat a heading (`## Notes`, `## Python`, `### Setup`)
    and a dict silently overwrote the first occurrence's body with the last
    one's -- losing a whole section before any merging began. `key` is
    `(heading, nth occurrence)`, so the Nth `## Notes` in one version is
    matched against the Nth `## Notes` in the other.

    Headings inside a fenced code block are not headings. See `_HEADING`.
    """
    sections = []
    seen = {}
    current_heading = _PREAMBLE
    current_lines: list = []
    in_fence = False

    def flush():
        occurrence = seen.get(current_heading, 0)
        seen[current_heading] = occurrence + 1
        sections.append(
            ((current_heading, occurrence), current_heading, "".join(current_lines))
        )

    for line in text.splitlines(keepends=True):
        if _FENCE.match(line.lstrip()):
            in_fence = not in_fence
            current_lines.append(line)
            continue
        if not in_fence and _HEADING.match(line):
            flush()
            current_heading = line.rstrip()
            current_lines = []
        else:
            current_lines.append(line)
    flush()
    return sections


def _section_union(version_a: str, version_b: str) -> str:
    """
    Section-aware merge: split both texts on markdown headings.

    Per section heading:
    - Only in A        → keep A's content
    - Only in B        → append B's section
    - Same heading, identical content → keep once
    - Same heading, DIFFERENT content → append unique lines from B to A's section.
      If there are outright contradictions (same-prefix lines with different values),
      emit <<<<<< conflict markers so the skill's conflict-resolution UX fires.
    """

    sections_a = _parse_sections(version_a)
    sections_b = _parse_sections(version_b)

    # Keyed by (heading, nth occurrence), never by the heading alone. Keying on
    # the heading made a document with two `## Notes` sections lose the first
    # one's body entirely -- the second overwrote it during parsing, before any
    # merging happened, and the loss was silent. Repeated headings are ordinary
    # in a CLAUDE.md or a rules file (`## Notes`, `## Python`, `### Setup`), so
    # the Nth `## Notes` in A is matched against the Nth `## Notes` in B.
    bodies_b = {key: body for key, heading, body in sections_b}
    matched_b = set()

    result_parts = []

    # Walk A's sections in order, merging B where headings collide
    for key, heading, body_a in sections_a:
        if key not in bodies_b:
            if heading != _PREAMBLE:
                result_parts.append(heading)
            result_parts.append(body_a)
            continue

        matched_b.add(key)
        body_b = bodies_b[key]
        if body_a.strip() == body_b.strip():
            # Identical — keep once
            if heading != _PREAMBLE:
                result_parts.append(heading)
            result_parts.append(body_a)
        else:
            # Different — line-union: keep A's lines, append unique lines from B.
            # A genuine conflict is only same-key/different-value on `key:` lines;
            # list bullets and prose always union (never fabricate a conflict).
            lines_a = body_a.splitlines()
            lines_b = body_b.splitlines()
            lines_a_stripped = {line.strip() for line in lines_a}
            line_keys_a = {}
            for line in lines_a:
                line_key = _line_key(line)
                if line_key is not None:
                    line_keys_a.setdefault(line_key, line)

            merged_lines = list(lines_a)
            conflicts = []
            for line_b in lines_b:
                if not line_b.strip() or line_b.strip() in lines_a_stripped:
                    continue
                line_key_b = _line_key(line_b)
                if (
                    line_key_b is not None
                    and line_key_b in line_keys_a
                    and line_keys_a[line_key_b].strip() != line_b.strip()
                ):
                    conflicts.append((line_keys_a[line_key_b], line_b))
                else:
                    merged_lines.append(line_b)

            if heading != _PREAMBLE:
                result_parts.append(heading)
            result_parts.append("\n".join(merged_lines))

            # Emit conflict markers for genuine contradictions
            for line_a_conflict, line_b_conflict in conflicts:
                result_parts.append(
                    f"\n{CONFLICT_MARKER}\n{line_a_conflict.strip()}\n"
                    f"=======\n{line_b_conflict.strip()}\n>>>>>>> Machine B\n"
                )

    # Append sections that only exist in B, in B's own order
    for key, heading, body_b in sections_b:
        if key not in matched_b:
            if heading != _PREAMBLE:
                result_parts.append(heading)
            result_parts.append(body_b)

    return _normalize_blank_lines("\n".join(result_parts))


# Three or more consecutive newlines collapse to a paragraph break.
_RUN_OF_BLANK_LINES = re.compile(r"\n{3,}")


def _normalize_blank_lines(text: str) -> str:
    """Collapse runs of blank lines and end with exactly one newline.

    Section bodies are parsed with their trailing newlines intact and then
    re-joined with another, so every fold added a blank line -- and
    `cmd_consolidate` folds its own previous output back in, making the growth
    unbounded across syncs. Normalising makes the merge idempotent on
    whitespace, which is what lets "nothing changed" actually produce an
    unchanged file.
    """
    return _RUN_OF_BLANK_LINES.sub("\n\n", text).rstrip("\n") + "\n"
