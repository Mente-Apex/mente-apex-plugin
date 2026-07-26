#!/usr/bin/env python3
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
            merge_log.append({"file": key, "strategy": strategy})

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


def _line_key(line: str):
    """Conflict identity of a line, or None if it can only be unioned.

    List items (-, *, +, `N.`) and blank lines never conflict — they union.
    Only `key: value` style lines carry an identity that can contradict.
    """
    stripped = line.strip()
    if not stripped or stripped[0] in "-*+" or re.match(r"\d+\.", stripped):
        return None
    match = re.match(r"([^:]+):", stripped)
    return match.group(1).strip() if match else None


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

    def _parse_sections(text: str) -> dict:
        """Return OrderedDict of {heading: content} preserving order."""
        from collections import OrderedDict

        sections: dict = OrderedDict()
        current_heading: str | None = "__preamble__"
        current_lines: list = []
        for line in text.splitlines(keepends=True):
            if line.startswith("#"):
                sections[current_heading] = "".join(current_lines)
                current_heading = line.rstrip()
                current_lines = []
            else:
                current_lines.append(line)
        sections[current_heading] = "".join(current_lines)
        return sections

    secs_a = _parse_sections(version_a)
    secs_b = _parse_sections(version_b)

    result_parts = []

    # Walk A's sections in order, merging B where headings collide
    for heading, body_a in secs_a.items():
        if heading not in secs_b:
            if heading != "__preamble__":
                result_parts.append(heading)
            result_parts.append(body_a)
            continue

        body_b = secs_b[heading]
        if body_a.strip() == body_b.strip():
            # Identical — keep once
            if heading != "__preamble__":
                result_parts.append(heading)
            result_parts.append(body_a)
        else:
            # Different — line-union: keep A's lines, append unique lines from B.
            # A genuine conflict is only same-key/different-value on `key:` lines;
            # list bullets and prose always union (never fabricate a conflict).
            lines_a = body_a.splitlines()
            lines_b = body_b.splitlines()
            lines_a_stripped = {line.strip() for line in lines_a}
            keys_a = {}
            for line in lines_a:
                key = _line_key(line)
                if key is not None:
                    keys_a.setdefault(key, line)

            merged_lines = list(lines_a)
            conflicts = []
            for line_b in lines_b:
                if not line_b.strip() or line_b.strip() in lines_a_stripped:
                    continue
                key_b = _line_key(line_b)
                if (
                    key_b is not None
                    and key_b in keys_a
                    and keys_a[key_b].strip() != line_b.strip()
                ):
                    conflicts.append((keys_a[key_b], line_b))
                else:
                    merged_lines.append(line_b)

            if heading != "__preamble__":
                result_parts.append(heading)
            result_parts.append("\n".join(merged_lines))

            # Emit conflict markers for genuine contradictions
            for line_a_conflict, line_b_conflict in conflicts:
                result_parts.append(
                    f"\n<<<<<<< Machine A\n{line_a_conflict.strip()}\n"
                    f"=======\n{line_b_conflict.strip()}\n>>>>>>> Machine B\n"
                )

    # Append sections that only exist in B
    for heading, body_b in secs_b.items():
        if heading not in secs_a:
            if heading != "__preamble__":
                result_parts.append(heading)
            result_parts.append(body_b)

    return "\n".join(result_parts)
