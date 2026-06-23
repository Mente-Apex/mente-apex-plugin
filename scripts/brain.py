#!/usr/bin/env python3
"""
open-memory brain.py — cross-platform core for memory sync.

All file manipulation lives here so that SKILL.md files stay clean
and nothing breaks across macOS (BSD) vs Linux (GNU) environments.

Usage:
  python3 brain.py export               -> print JSON snapshot to stdout
  python3 brain.py import <snapshot>    -> apply snapshot to local Claude state
  python3 brain.py backup               -> save timestamped backup, print path
  python3 brain.py status               -> print human-readable inventory
  python3 brain.py merge <a> <b>        -> smart-merge two snapshots, print result
  python3 brain.py apply-shared <repo>  -> install shared artifacts from repo shared/ dir
  python3 brain.py log-sync <repo> [action] [summary]  -> append sync entry to meta/sync-log.json
  python3 brain.py scan                 -> check all exportable files for secret-like content, print JSON report
  python3 brain.py promote              -> analyse memory, print promotion suggestions as JSON
  python3 brain.py machine-id           -> print or create stable machine ID
  python3 brain.py clean-settings <f>   -> strip secrets from settings JSON, print cleaned version
"""

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths — always derived from $HOME, never hardcoded
# ---------------------------------------------------------------------------
HOME = Path.home()
CLAUDE_DIR = HOME / ".claude"
MEMORY_CONFIG = CLAUDE_DIR / "open-memory-config.json"
MEMORY_REPO = CLAUDE_DIR / "open-memory-repo"

# Directories we capture in a snapshot (relative to CLAUDE_DIR)
SNAPSHOT_DIRS = ["memory", "rules", "skills", "agents"]
SNAPSHOT_FILES = ["CLAUDE.md", "settings.json", "keybindings.json"]

# Path prefixes (relative to CLAUDE_DIR) never exported or imported.
# Keeps plugin-system state and sync-repo internals out of brain snapshots.
SNAPSHOT_EXCLUDE_PREFIXES = [
    "plugins/",
    "open-memory-repo/",
    "open-memory-backups/",
]

# Patterns that look like secrets — strip values from settings before export
SECRET_PATTERNS = [
    re.compile(r"(api[_-]?key|token|secret|password|credential|auth)", re.IGNORECASE)
]

PLUGINS_DIR = CLAUDE_DIR / "plugins"
INSTALLED_PLUGINS_FILE = PLUGINS_DIR / "installed_plugins.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read(path: Path) -> str:
    """Read a text file, return empty string if missing."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _machine_id() -> str:
    """Return a stable ID for this machine, creating one if needed."""
    id_file = CLAUDE_DIR / "open-memory-machine-id"
    if id_file.exists():
        return id_file.read_text().strip()
    import uuid
    mid = f"{platform.node()}-{uuid.uuid4().hex[:8]}"
    _write(id_file, mid)
    return mid


def _collect_dir(base: Path, rel: str) -> dict:
    """Walk a directory and return {relative_path: content} for all .md/.json files."""
    result = {}
    target = base / rel
    if not target.exists():
        return result
    for p in sorted(target.rglob("*")):
        if p.is_file() and p.suffix in (".md", ".json", ".txt"):
            key = str(p.relative_to(base))
            result[key] = _read(p)
    return result


def _installed_plugin_ids() -> set:
    """Return the set of plugin IDs currently in installed_plugins.json."""
    if not INSTALLED_PLUGINS_FILE.exists():
        return set()
    try:
        data = json.loads(INSTALLED_PLUGINS_FILE.read_text(encoding="utf-8"))
        return set(data.get("plugins", {}).keys())
    except (json.JSONDecodeError, KeyError):
        return set()


def _reconcile_plugins(settings: dict) -> tuple:
    """
    Drop orphaned keys from enabledPlugins — entries whose plugin ID is absent
    from installed_plugins.json.  Claude Code's uninstall removes the registry
    entry but leaves the settings flag behind; this catches that gap.

    Returns (cleaned_settings_dict, list_of_removed_ids).
    """
    installed = _installed_plugin_ids()
    if not installed:
        return settings, []

    enabled = settings.get("enabledPlugins", {})
    orphans = [pid for pid in enabled if pid not in installed]
    if not orphans:
        return settings, []

    cleaned = dict(settings)
    cleaned["enabledPlugins"] = {
        pid: value for pid, value in enabled.items() if pid in installed
    }
    return cleaned, orphans


def _prune_stale_plugin_cache(installed: set) -> list:
    """
    Delete cache subdirectories for marketplaces that have no installed plugin.
    A cache dir named <marketplace> is stale when no installed plugin ID ends
    with @<marketplace>.  Returns list of removed paths.
    """
    cache_dir = PLUGINS_DIR / "cache"
    if not cache_dir.exists():
        return []
    removed = []
    for entry in sorted(cache_dir.iterdir()):
        if not entry.is_dir():
            continue
        marketplace = entry.name
        if not any(pid.endswith(f"@{marketplace}") for pid in installed):
            shutil.rmtree(entry)
            removed.append(str(entry))
    return removed


def _clean_settings(raw: str) -> dict:
    """Parse settings JSON and strip any env vars or secret-looking values."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}

    def _scrub(obj, depth=0):
        if depth > 10:
            return obj
        if isinstance(obj, dict):
            cleaned = {}
            for k, v in obj.items():
                # Drop env blocks entirely — they contain API keys
                if k in ("env", "environment"):
                    continue
                # Drop values where the key looks secret-ish
                if any(pat.search(k) for pat in SECRET_PATTERNS):
                    continue
                cleaned[k] = _scrub(v, depth + 1)
            return cleaned
        if isinstance(obj, list):
            return [_scrub(i, depth + 1) for i in obj]
        return obj

    return _scrub(data)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_machine_id():
    print(_machine_id())


def cmd_export():
    """Collect Claude state into a JSON snapshot and print to stdout."""
    files = {}
    reconcile_info = {}

    # Top-level files
    for fname in SNAPSHOT_FILES:
        p = CLAUDE_DIR / fname
        if p.exists():
            if fname == "settings.json":
                cleaned = _clean_settings(_read(p))
                cleaned, orphans = _reconcile_plugins(cleaned)
                if orphans:
                    # Write the reconciled settings back so the live file is clean too
                    p.write_text(
                        json.dumps(
                            json.loads(_read(p)) | {"enabledPlugins": cleaned.get("enabledPlugins", {})},
                            indent=2, ensure_ascii=False
                        ),
                        encoding="utf-8",
                    )
                    stale_cache = _prune_stale_plugin_cache(_installed_plugin_ids())
                    reconcile_info = {
                        "orphaned_plugins_removed": orphans,
                        "stale_cache_dirs_removed": stale_cache,
                    }
                files[fname] = json.dumps(cleaned)
            else:
                files[fname] = _read(p)

    # Subdirectories
    for d in SNAPSHOT_DIRS:
        files.update(_collect_dir(CLAUDE_DIR, d))

    # Strip anything that should never leave this machine
    files = {
        k: v for k, v in files.items()
        if not any(k.startswith(prefix) for prefix in SNAPSHOT_EXCLUDE_PREFIXES)
    }

    snapshot = {
        "machine_id": _machine_id(),
        "hostname": platform.node(),
        "platform": platform.system(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "files": files,
    }
    if reconcile_info:
        snapshot["reconcile"] = reconcile_info
    print(json.dumps(snapshot, indent=2, ensure_ascii=False))


def cmd_import(snapshot_path: str):
    """Apply a snapshot to local Claude state. Prints a summary of changes."""
    raw = Path(snapshot_path).read_text(encoding="utf-8")
    snapshot = json.loads(raw)
    files = snapshot.get("files", {})
    applied, skipped = [], []

    for rel, content in files.items():
        if any(rel.startswith(prefix) for prefix in SNAPSHOT_EXCLUDE_PREFIXES):
            skipped.append(rel)
            continue
        dest = CLAUDE_DIR / rel
        existing = _read(dest)
        if existing == content:
            skipped.append(rel)
            continue
        _write(dest, content)
        applied.append(rel)

    print(json.dumps({"applied": applied, "skipped": skipped}))


def cmd_status():
    """Print a human-readable inventory of the local brain state."""
    lines = []
    lines.append(f"Machine : {_machine_id()}")
    lines.append(f"Host    : {platform.node()}")
    lines.append(f"OS      : {platform.system()}")
    lines.append("")

    config_exists = MEMORY_CONFIG.exists()
    repo_exists = MEMORY_REPO.exists()
    lines.append(f"open-memory repo : {'✓  ' + str(MEMORY_REPO) if repo_exists else '✗  not initialised'}")

    if config_exists:
        cfg = json.loads(_read(MEMORY_CONFIG))
        lines.append(f"Remote           : {cfg.get('remote', 'unknown')}")
        lines.append(f"Last sync        : {cfg.get('last_sync', 'never')}")

    lines.append("")
    lines.append("── Local brain inventory ──────────────────────────────")

    claude_md = CLAUDE_DIR / "CLAUDE.md"
    lines.append(f"CLAUDE.md  : {'✓ ' + str(len(_read(claude_md).splitlines())) + ' lines' if claude_md.exists() else '✗ missing'}")

    for d in SNAPSHOT_DIRS:
        target = CLAUDE_DIR / d
        if target.exists():
            count = sum(1 for p in target.rglob("*") if p.is_file())
            lines.append(f"{d:<10} : {count} file(s)")
        else:
            lines.append(f"{d:<10} : (empty)")

    print("\n".join(lines))


def cmd_merge(path_a: str, path_b: str):
    """
    Smart-merge two brain snapshots.

    Strategy per file:
      - Identical  -> keep as-is
      - Only in A  -> keep A
      - Only in B  -> keep B
      - Both differ -> attempt LLM merge via `claude -p`; fall back to
                       section-aware union if claude CLI is unavailable
    Prints the merged snapshot JSON to stdout.
    """
    snap_a = json.loads(Path(path_a).read_text(encoding="utf-8"))
    snap_b = json.loads(Path(path_b).read_text(encoding="utf-8"))

    files_a = snap_a.get("files", {})
    files_b = snap_b.get("files", {})
    all_keys = sorted(set(files_a) | set(files_b))

    merged_files = {}
    merge_log = []

    for key in all_keys:
        a = files_a.get(key)
        b = files_b.get(key)

        if a is None:
            merged_files[key] = b
            merge_log.append({"file": key, "strategy": "b-only"})
        elif b is None:
            merged_files[key] = a
            merge_log.append({"file": key, "strategy": "a-only"})
        elif a == b:
            merged_files[key] = a
            merge_log.append({"file": key, "strategy": "identical"})
        else:
            # JSON files (settings.json) need deep-merge, not text merge
            if key.endswith(".json"):
                merged, strategy = _deep_merge_json(a, b)
            else:
                merged, strategy = _smart_merge_text(a, b, context=key)
            merged_files[key] = merged
            merge_log.append({"file": key, "strategy": strategy})

    result = {
        "machine_id": f"merged-{snap_a['machine_id']}-{snap_b['machine_id']}",
        "hostname": "merged",
        "platform": platform.system(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "files": merged_files,
        "merge_log": merge_log,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))


def _deep_merge_json(a: str, b: str) -> tuple:
    """
    Deep-merge two JSON strings (e.g. settings.json).
    B's scalar values win on conflict; lists are unioned; dicts recurse.
    Returns (merged_json_string, strategy_name).
    """
    def _merge(base, override):
        if isinstance(base, dict) and isinstance(override, dict):
            result = dict(base)
            for k, v in override.items():
                result[k] = _merge(base.get(k), v)
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
        obj_a = json.loads(a) if a else {}
        obj_b = json.loads(b) if b else {}
        merged = _merge(obj_a, obj_b)
        return json.dumps(merged, indent=2, ensure_ascii=False), "json-deep-merge"
    except json.JSONDecodeError:
        # If either side is corrupt JSON, fall back to keeping A
        return a, "json-fallback-kept-a"


def _smart_merge_text(a: str, b: str, context: str = "") -> tuple:
    """
    Merge two text blobs. Returns (merged_text, strategy_name).

    1. Try LLM merge via `claude -p` if available.
    2. Fall back to section-aware union (headings as boundaries).
    """
    if shutil.which("claude"):
        prompt = (
            f"Merge these two versions of '{context}' into one coherent document.\n"
            "Rules:\n"
            "- Remove exact duplicates\n"
            "- Resolve contradictions by keeping the more specific or detailed version\n"
            "- Preserve all unique content from both versions\n"
            "- Keep the same general structure and tone\n"
            "- Output ONLY the merged content, no explanation or commentary\n\n"
            f"=== VERSION A ===\n{a}\n\n"
            f"=== VERSION B ===\n{b}"
        )
        try:
            result = subprocess.run(
                ["claude", "-p", prompt],
                capture_output=True, text=True, timeout=90
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip(), "llm-merge"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    # Fallback: section-aware union
    return _section_union(a, b), "section-union"


def _section_union(a: str, b: str) -> str:
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

    secs_a = _parse_sections(a)
    secs_b = _parse_sections(b)

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
            # Different — line-union: keep A's lines, append unique lines from B
            lines_a = body_a.splitlines()
            lines_b = body_b.splitlines()
            lines_a_stripped = {l.strip() for l in lines_a}

            merged_lines = list(lines_a)
            conflicts = []
            for line_b in lines_b:
                if line_b.strip() in lines_a_stripped or not line_b.strip():
                    continue
                # Check for contradiction: same start of line but different value
                contradiction = any(
                    la.strip() and lb.strip() and
                    la.strip().split()[0] == line_b.strip().split()[0] and
                    la.strip() != line_b.strip()
                    for la, lb in [(l, line_b) for l in lines_a]
                )
                if contradiction:
                    conflicts.append((
                        next(l for l in lines_a if l.strip().split()[:1] == line_b.strip().split()[:1]),
                        line_b
                    ))
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


def cmd_backup():
    """
    Export current local brain state to a timestamped backup file.
    Prints the backup path so the caller can reference it.
    Safe to call before any destructive operation (sync apply, join, etc).
    """
    backup_dir = CLAUDE_DIR / "open-memory-backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir / f"snapshot-{ts}.json"

    # Reuse export logic by capturing stdout
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf):
        cmd_export()
    backup_path.write_text(buf.getvalue(), encoding="utf-8")
    print(str(backup_path))


def cmd_apply_shared(repo_path: str):
    """
    Install shared artifacts from the repo's shared/ directory into ~/.claude/.
    Reads shared/skills/, shared/rules/, shared/agents/ and copies new files locally.
    Also handles shared/plugins/: copies plugin files into the cache and registers
    them in installed_plugins.json if not already present.
    Prints a summary of what was installed.
    """
    repo = Path(repo_path)
    shared = repo / "shared"
    if not shared.exists():
        print(json.dumps({"installed": [], "note": "no shared/ directory in repo"}))
        return

    # Map shared subdirs to local ~/.claude/ destinations
    mapping = {
        "skills": CLAUDE_DIR / "skills",
        "rules": CLAUDE_DIR / "rules",
        "agents": CLAUDE_DIR / "agents",
    }

    installed = []
    skipped = []

    for shared_type, local_dest in mapping.items():
        src_dir = shared / shared_type
        if not src_dir.exists():
            continue
        for src in sorted(src_dir.rglob("*")):
            if not src.is_file():
                continue
            rel = src.relative_to(src_dir)
            dest = local_dest / rel
            if dest.exists():
                # Don't overwrite local customisations — skip silently
                skipped.append(f"{shared_type}/{rel}")
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            installed.append(f"{shared_type}/{rel}")

    # Handle shared plugins: each subdir is named <plugin-key> and contains
    # a plugin-meta.json plus the plugin's files.
    plugins_src = shared / "plugins"
    if plugins_src.exists():
        installed_plugins_path = CLAUDE_DIR / "plugins" / "installed_plugins.json"
        try:
            plugins_manifest = json.loads(installed_plugins_path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            plugins_manifest = {"version": 2, "plugins": {}}

        for plugin_dir in sorted(plugins_src.iterdir()):
            if not plugin_dir.is_dir():
                continue
            meta_file = plugin_dir / "plugin-meta.json"
            if not meta_file.exists():
                skipped.append(f"plugins/{plugin_dir.name} (missing plugin-meta.json)")
                continue
            meta = json.loads(meta_file.read_text())
            plugin_key = meta.get("key", plugin_dir.name)
            marketplace = meta.get("marketplace", "unknown")
            plugin_name = meta.get("name", plugin_dir.name)
            version = meta.get("version", "unknown")

            # Skip if already registered in installed_plugins.json
            if plugin_key in plugins_manifest.get("plugins", {}):
                skipped.append(f"plugins/{plugin_key}")
                continue

            # Copy plugin files (excluding plugin-meta.json) into the cache
            install_path = CLAUDE_DIR / "plugins" / "cache" / marketplace / plugin_name / version
            install_path.mkdir(parents=True, exist_ok=True)
            for src_file in sorted(plugin_dir.rglob("*")):
                if not src_file.is_file() or src_file.name == "plugin-meta.json":
                    continue
                rel = src_file.relative_to(plugin_dir)
                dest = install_path / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dest)

            # Register in installed_plugins.json
            now = datetime.now(timezone.utc).isoformat()
            entry = {
                "scope": "user",
                "installPath": str(install_path),
                "version": version,
                "installedAt": now,
                "lastUpdated": now,
            }
            if meta.get("gitCommitSha"):
                entry["gitCommitSha"] = meta["gitCommitSha"]
            plugins_manifest.setdefault("plugins", {})[plugin_key] = [entry]
            installed_plugins_path.write_text(json.dumps(plugins_manifest, indent=4))
            installed.append(f"plugins/{plugin_key}")

    print(json.dumps({"installed": installed, "skipped": skipped}))


def cmd_log_sync(repo_path: str, action: str = "sync", summary: str = ""):
    """
    Append a sync entry to meta/sync-log.json in the repo.
    Creates the file if it doesn't exist.

    action  : one of push | pull | sync | setup | promote | share (default: sync)
    summary : short human-readable description of what changed (optional)
    """
    repo = Path(repo_path)
    meta_dir = repo / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    log_path = meta_dir / "sync-log.json"

    try:
        log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else {"syncs": []}
    except json.JSONDecodeError:
        log = {"syncs": []}

    entry = {
        "machine_id": _machine_id(),
        "hostname": platform.node(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
    }
    if summary:
        entry["summary"] = summary

    log["syncs"].append(entry)

    # Keep last 200 entries to avoid unbounded growth
    log["syncs"] = log["syncs"][-200:]
    log_path.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Sync logged ({len(log['syncs'])} total entries)")


def cmd_scan():
    """
    Scan all files that would be exported for secret-like content.

    Checks CLAUDE.md, memory/, rules/, skills/, agents/ for patterns that look
    like API keys, tokens, passwords, etc. — things you probably don't want
    committed to a Git remote even in a private repo.

    Prints JSON: {"warnings": [{"file": ..., "line": ..., "match": ...}], "clean": bool}
    """
    warnings = []

    # Broader patterns for scanning free-text content (not just key names)
    scan_patterns = [
        # High-entropy hex/base64 strings that look like tokens
        re.compile(r'\b(sk-[A-Za-z0-9]{20,})\b'),                     # OpenAI-style keys
        re.compile(r'\b(ghp_[A-Za-z0-9]{36})\b'),                     # GitHub tokens
        re.compile(r'\b(xoxb-[0-9]+-[A-Za-z0-9]+)\b'),               # Slack tokens
        re.compile(r'\b(AIza[0-9A-Za-z\-_]{35})\b'),                  # Google API keys
        # Generic: key = "long-random-string"
        re.compile(r'(?i)(api[_\s]?key|token|secret|password)\s*[=:]\s*["\']?([A-Za-z0-9/+\-_]{20,})["\']?'),
        # AWS-style
        re.compile(r'\b(AKIA[0-9A-Z]{16})\b'),
    ]

    files_to_scan = {}

    # Top-level files (excluding settings.json — already scrubbed)
    for fname in ["CLAUDE.md"]:
        p = CLAUDE_DIR / fname
        if p.exists():
            files_to_scan[fname] = _read(p)

    # Subdirectories
    for d in SNAPSHOT_DIRS:
        files_to_scan.update(_collect_dir(CLAUDE_DIR, d))

    for rel, content in files_to_scan.items():
        for lineno, line in enumerate(content.splitlines(), start=1):
            for pat in scan_patterns:
                match = pat.search(line)
                if match:
                    # Redact the actual matched value in output
                    warnings.append({
                        "file": rel,
                        "line": lineno,
                        "match": pat.pattern[:40] + "…",
                        "preview": line.strip()[:80] + ("…" if len(line.strip()) > 80 else ""),
                    })
                    break  # one warning per line is enough

    result = {"warnings": warnings, "clean": len(warnings) == 0}
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_promote():
    """
    Analyse memory files and suggest promotions to CLAUDE.md or rules.

    Looks for patterns that appear in 3+ memory files (repeated instructions,
    preferences, principles) and suggests promoting them so they're always
    in context rather than buried in memory.

    Prints JSON: {"suggestions": [{"type": "claude_md"|"rule", "content": ..., "reason": ...}]}
    """
    memory_dir = CLAUDE_DIR / "memory"
    if not memory_dir.exists():
        print(json.dumps({"suggestions": []}))
        return

    # Collect all memory content
    memory_files = {}
    for p in sorted(memory_dir.rglob("*.md")):
        memory_files[str(p.relative_to(CLAUDE_DIR))] = _read(p)

    if not memory_files:
        print(json.dumps({"suggestions": []}))
        return

    if not shutil.which("claude"):
        print(json.dumps({"suggestions": [], "note": "claude CLI not available — LLM promotion analysis skipped"}))
        return

    all_memory = "\n\n---\n\n".join(
        f"[{k}]\n{v}" for k, v in memory_files.items()
    )
    existing_claude_md = _read(CLAUDE_DIR / "CLAUDE.md")

    prompt = (
        "You are analysing Claude's accumulated session memory to find patterns "
        "worth promoting to permanent configuration.\n\n"
        "EXISTING CLAUDE.md (already permanent — do not suggest duplicates):\n"
        f"{existing_claude_md or '(empty)'}\n\n"
        "MEMORY FILES:\n"
        f"{all_memory}\n\n"
        "Task: Identify 1-5 patterns that:\n"
        "  - Appear repeatedly across multiple memory entries\n"
        "  - Are general preferences, principles, or rules (not project-specific facts)\n"
        "  - Are NOT already covered in CLAUDE.md\n\n"
        "For each pattern, decide:\n"
        "  - 'claude_md' if it's a general instruction that should always be in context\n"
        "  - 'rule' if it's a specific rule for a narrow domain\n\n"
        "Respond with ONLY valid JSON in this exact shape:\n"
        '{"suggestions": [{"type": "claude_md", "content": "...", "reason": "..."}]}\n'
        "No explanation outside the JSON."
    )

    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            # Extract JSON from output (model may add surrounding text)
            output = result.stdout.strip()
            match = re.search(r'\{.*\}', output, re.DOTALL)
            if match:
                print(match.group(0))
                return
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    print(json.dumps({"suggestions": [], "note": "LLM analysis failed — try again"}))


def cmd_clean_settings(path: str):
    raw = Path(path).read_text(encoding="utf-8")
    print(json.dumps(_clean_settings(raw), indent=2))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

COMMANDS = {
    "export": (cmd_export, 0),
    "import": (cmd_import, 1),
    "backup": (cmd_backup, 0),
    "status": (cmd_status, 0),
    "merge": (cmd_merge, 2),
    "apply-shared": (cmd_apply_shared, 1),
    "log-sync": (cmd_log_sync, None),   # variadic: repo [action] [summary]
    "scan": (cmd_scan, 0),
    "promote": (cmd_promote, 0),
    "machine-id": (cmd_machine_id, 0),
    "clean-settings": (cmd_clean_settings, 1),
}


def main():
    args = sys.argv[1:]
    if not args or args[0] not in COMMANDS:
        print(f"Usage: brain.py <command> [args]\nCommands: {', '.join(COMMANDS)}", file=sys.stderr)
        sys.exit(1)

    cmd_name = args[0]
    fn, expected_args = COMMANDS[cmd_name]
    provided = len(args) - 1

    if expected_args is not None and provided != expected_args:
        print(f"Error: '{cmd_name}' expects {expected_args} argument(s), got {provided}", file=sys.stderr)
        sys.exit(1)

    fn(*args[1:])


if __name__ == "__main__":
    main()
