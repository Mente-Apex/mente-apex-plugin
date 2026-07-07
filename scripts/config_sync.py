#!/usr/bin/env python3
"""
config_sync.py — cross-platform core for Claude config sync.

Syncs your ~/.claude config files (CLAUDE.md, rules/, skills/, agents/,
memory/ files, settings.json) across machines via a private Git repo.
This is NOT the knowledge brain — for capturing/recalling facts use the
`mem` CLI / the mente-apex-memory MCP server (/memory).

All file manipulation lives here so that SKILL.md files stay clean
and nothing breaks across macOS (BSD) vs Linux (GNU) environments.

Usage:
  python3 config_sync.py export               -> print JSON snapshot to stdout
  python3 config_sync.py import <snapshot>    -> apply snapshot to local Claude state
  python3 config_sync.py backup               -> save timestamped backup, print path
  python3 config_sync.py status               -> print human-readable inventory
  python3 config_sync.py merge <a> <b>        -> smart-merge two snapshots, print result
  python3 config_sync.py apply-shared <repo>  -> install shared artifacts from repo shared/ dir
  python3 config_sync.py log-sync <repo> [action] [summary]  -> append sync entry to meta/sync-log.json
  python3 config_sync.py scan                 -> check all exportable files for secret-like content, print JSON report
  python3 config_sync.py promote              -> analyse memory, print promotion suggestions as JSON
  python3 config_sync.py machine-id           -> print or create stable machine ID
  python3 config_sync.py clean-settings <f>   -> strip secrets from settings JSON, print cleaned version
  python3 config_sync.py migrate              -> rename legacy open-memory-* paths to config-sync-* (idempotent)
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
from typing import TYPE_CHECKING, Optional, Protocol

# The text/JSON merge engine lives in its own module (SRP extraction). Re-exported
# here so cmd_merge/cmd_consolidate and existing callers keep using the config_sync.*
# names while the algorithm is read and maintained in one focused place.
from config_sync_merge import (
    LLM_MERGE_ENV,
    _merge_snapshot_files,
    _deep_merge_json,
    _LlmMergeBudget,
    _smart_merge_text,
    _line_key,
    _section_union,
)

if TYPE_CHECKING:
    # Runtime-free import (TYPE_CHECKING is False at import time) so cmd_status can
    # name BundleExportFilter in an annotation without forming the config_sync <->
    # config_sync_propagators import cycle (SOLID M2).
    from config_sync_propagators import BundleExportFilter

# ---------------------------------------------------------------------------
# Paths — always derived from $HOME, never hardcoded
# ---------------------------------------------------------------------------
HOME = Path.home()
CLAUDE_DIR = HOME / ".claude"
CONFIG_FILE = CLAUDE_DIR / "config-sync-config.json"
CONFIG_REPO = CLAUDE_DIR / "config-sync-repo"

# Directories we capture in a snapshot (relative to CLAUDE_DIR)
SNAPSHOT_DIRS = ["memory", "rules", "skills", "agents"]
SNAPSHOT_FILES = ["CLAUDE.md", "settings.json", "keybindings.json"]

# Path prefixes (relative to CLAUDE_DIR) never exported or imported.
# Keeps plugin-system state and sync-repo internals out of snapshots.
SNAPSHOT_EXCLUDE_PREFIXES = [
    "plugins/",
    "config-sync-repo/",
    "config-sync-backups/",
]

# Patterns that look like secrets — strip values from settings before export
SECRET_PATTERNS = [
    re.compile(r"(api[_-]?key|token|secret|password|credential|auth)", re.IGNORECASE)
]

PLUGINS_DIR = CLAUDE_DIR / "plugins"
INSTALLED_PLUGINS_FILE = PLUGINS_DIR / "installed_plugins.json"

# Cap on nested `claude -p` merges per consolidate run. The LLM_MERGE_ENV toggle
# and the merge algorithm itself live in config_sync_merge (SRP); this is just the
# budget that cmd_consolidate spends.
MAX_LLM_MERGES = 10


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


def _is_within(path: Path, root: Path) -> bool:
    """True if `path` resolves to `root` itself or somewhere beneath it."""
    resolved = path.resolve()
    root_resolved = root.resolve()
    return resolved == root_resolved or resolved.is_relative_to(root_resolved)


def _safe_dest(rel: str):
    """Resolve `rel` under CLAUDE_DIR; return None if it escapes the tree.

    Guards against `../` traversal and absolute keys (`CLAUDE_DIR / "/abs"`
    discards the left side) in snapshots that were hand-edited or corrupted.
    """
    candidate = CLAUDE_DIR / rel
    return candidate if _is_within(candidate, CLAUDE_DIR) else None


def _machine_id() -> str:
    """Return a stable ID for this machine, creating one if needed."""
    id_file = CLAUDE_DIR / "config-sync-machine-id"
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
    for path in sorted(target.rglob("*")):
        if path.is_file() and path.suffix in (".md", ".json", ".txt"):
            key = str(path.relative_to(base))
            result[key] = _read(path)
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


def _derive_plugin_meta(plugin_key: str, entry: dict) -> dict:
    """Best-effort {key,marketplace,name,version[,gitCommitSha]} for a plugin.

    Prefers the cache path layout `.../cache/<marketplace>/<name>/<version>/`;
    falls back to the key (`name@marketplace`) and the registry entry's version
    when the installPath has no `cache` segment (a dev/linked plugin) — so
    sharing never crashes with an uncaught StopIteration.
    """
    parts = Path(entry.get("installPath", "")).parts
    marketplace = name = version = None
    if "cache" in parts:
        cache_index = parts.index("cache")
        segments = parts[cache_index + 1:cache_index + 4]
        if len(segments) == 3:
            marketplace, name, version = segments
    if name is None or marketplace is None:
        key_parts = plugin_key.split("@", 1)
        name = key_parts[0]
        marketplace = key_parts[1] if len(key_parts) > 1 else "unknown"
    if version is None:
        version = entry.get("version", "unknown")

    meta = {"key": plugin_key, "marketplace": marketplace, "name": name, "version": version}
    if entry.get("gitCommitSha"):
        meta["gitCommitSha"] = entry["gitCommitSha"]
    return meta


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
            for key, value in obj.items():
                # Drop env blocks entirely — they contain API keys
                if key in ("env", "environment"):
                    continue
                # Drop values where the key looks secret-ish
                if any(pattern.search(key) for pattern in SECRET_PATTERNS):
                    continue
                cleaned[key] = _scrub(value, depth + 1)
            return cleaned
        if isinstance(obj, list):
            return [_scrub(item, depth + 1) for item in obj]
        return obj

    return _scrub(data)


def _merge_import_settings(incoming_scrubbed: dict, existing_local: dict) -> dict:
    """Overlay the snapshot's (secret-scrubbed) settings onto the live local file.

    Start from the live local dict so env/apiKeyHelper/secret keys — which the
    export deliberately omits — are never deleted. Incoming non-secret fields win
    (they are the merged network truth). Consistent with the union-only contract:
    import adds/updates, never deletes.
    """
    merged = dict(existing_local)
    for key, value in incoming_scrubbed.items():
        merged[key] = value
    return merged


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_machine_id():
    print(_machine_id())


def cmd_export():
    """Collect Claude state into a JSON snapshot and print to stdout.

    Effectively a query: it reads local state and prints a snapshot. Its only
    side effect is creating the stable machine-id file on a machine's very first
    run (via `_machine_id`); it never drops orphaned plugins or prunes stale
    caches — that is the job of the explicit `reconcile` command (Command-Query
    Separation), so `backup` stays safe.
    """
    files = {}

    # Top-level files
    for fname in SNAPSHOT_FILES:
        path = CLAUDE_DIR / fname
        if path.exists():
            if fname == "settings.json":
                cleaned = _clean_settings(_read(path))
                cleaned, _orphans = _reconcile_plugins(cleaned)  # in-memory only for the snapshot
                files[fname] = json.dumps(cleaned)
            else:
                files[fname] = _read(path)

    # Subdirectories
    for directory in SNAPSHOT_DIRS:
        files.update(_collect_dir(CLAUDE_DIR, directory))

    # Strip anything that should never leave this machine
    files = {
        rel: content for rel, content in files.items()
        if not any(rel.startswith(prefix) for prefix in SNAPSHOT_EXCLUDE_PREFIXES)
    }

    snapshot = {
        "machine_id": _machine_id(),
        "hostname": platform.node(),
        "platform": platform.system(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "files": files,
    }
    print(json.dumps(snapshot, indent=2, ensure_ascii=False))


def cmd_reconcile():
    """Reconcile local plugin state (mutating) — the command half of D6.

    Drops orphaned enabledPlugins entries from the live settings.json (keeping
    env/secret keys intact) and prunes stale plugin cache dirs. Split out of
    `export` so a snapshot/backup never carries surprise side effects.
    """
    settings_path = CLAUDE_DIR / "settings.json"
    orphans = []
    stale_cache = []
    if settings_path.exists():
        raw = _read(settings_path)
        reconciled, orphans = _reconcile_plugins(_clean_settings(raw))
        if orphans:
            live = json.loads(raw)
            live["enabledPlugins"] = reconciled.get("enabledPlugins", {})
            settings_path.write_text(
                json.dumps(live, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            stale_cache = _prune_stale_plugin_cache(_installed_plugin_ids())
    print(json.dumps({
        "orphaned_plugins_removed": orphans,
        "stale_cache_dirs_removed": stale_cache,
    }))


def _apply_snapshot_file(dest: Path, relative_path: str, content: str) -> str:
    """Apply one snapshot file to `dest`; return "applied" or "skipped".

    settings.json is JSON-merged with the local copy (env/secret keys are already
    stripped on export) and written only when the merge changes it; every other
    file is written only when its content differs. This is the single per-file
    apply policy shared by `cmd_import` and `SnapshotPropagator.apply`, so the two
    entry points can never drift — adding a second merge-eligible file is one edit
    here, not two.
    """
    if relative_path == "settings.json":
        incoming = json.loads(content) if content.strip() else {}
        local_raw = _read(dest)
        existing_local = json.loads(local_raw) if local_raw.strip() else {}
        merged = json.dumps(
            _merge_import_settings(incoming, existing_local), indent=2, ensure_ascii=False)
        if local_raw == merged:
            return "skipped"
        _write(dest, merged)
        return "applied"
    if _read(dest) == content:
        return "skipped"
    _write(dest, content)
    return "applied"


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
        dest = _safe_dest(rel)
        if dest is None:
            skipped.append(rel)
            continue
        outcome = _apply_snapshot_file(dest, rel, content)
        (applied if outcome == "applied" else skipped).append(rel)

    print(json.dumps({"applied": applied, "skipped": skipped}))


def _inventory_file_count(target, export_filter):
    """Count files under `target`, excluding the vendored/build/scratch the export
    filter rejects — so `status` reports a skill/agent's authored files, not a
    virtualenv left inside a skill dir (#44). Uses the SAME filter as the bundle
    export, so the inventory count and what actually syncs agree."""
    return sum(
        1 for path in target.rglob("*")
        if path.is_file() and export_filter.should_include(path.relative_to(target).as_posix())
    )


class RemoteResolver(Protocol):
    """Abstraction over 'what is this repo's remote URL'. cmd_status depends on
    this port, never on git directly, so the subprocess boundary can be faked in
    tests and swapped for a different VCS without touching status-formatting."""

    def resolve(self, repo_path: Path) -> Optional[str]:
        ...


class GitRemoteResolver:
    """Resolves a repo's origin URL via `git remote get-url origin` — the actual
    source of truth, replacing a `remote` config key that setup never wrote and
    that made status print `unknown` for every user (#48). Returns None when the
    repo is absent or has no origin, so callers render 'not configured'."""

    def resolve(self, repo_path: Path) -> Optional[str]:
        if not repo_path.exists():
            return None
        completed = subprocess.run(
            ["git", "-C", str(repo_path), "remote", "get-url", "origin"],
            capture_output=True, text=True,
        )
        if completed.returncode != 0:
            return None
        url = completed.stdout.strip()
        return url or None


def cmd_status(remote_resolver: Optional[RemoteResolver] = None,
               export_filter: "Optional[BundleExportFilter]" = None):
    """Print a human-readable inventory of the local config-sync state.

    Both collaborators are injected (defaults: git-backed remote lookup, default
    bundle filter) so they are substitutable — the CLI passes nothing and gets the
    real implementations, while a test can fake either one."""
    if remote_resolver is None:
        remote_resolver = GitRemoteResolver()
    if export_filter is None:
        # Deferred import: config_sync <-> config_sync_propagators is a two-way
        # dependency; keep it call-time (SOLID M2).
        from config_sync_propagators import DefaultBundleExportFilter
        export_filter = DefaultBundleExportFilter()
    lines = []
    lines.append(f"Machine : {_machine_id()}")
    lines.append(f"Host    : {platform.node()}")
    lines.append(f"OS      : {platform.system()}")
    lines.append("")

    config_exists = CONFIG_FILE.exists()
    repo_exists = CONFIG_REPO.exists()
    lines.append(f"config-sync repo : {'✓  ' + str(CONFIG_REPO) if repo_exists else '✗  not initialised'}")

    if config_exists:
        cfg = json.loads(_read(CONFIG_FILE))
        remote_url = remote_resolver.resolve(CONFIG_REPO)
        lines.append(f"Remote           : {remote_url if remote_url else 'not configured'}")
        lines.append(f"Last sync        : {cfg.get('last_sync', 'never')}")

    lines.append("")
    lines.append("── Local config inventory ─────────────────────────────")

    claude_md = CLAUDE_DIR / "CLAUDE.md"
    lines.append(f"CLAUDE.md  : {'✓ ' + str(len(_read(claude_md).splitlines())) + ' lines' if claude_md.exists() else '✗ missing'}")

    for directory in SNAPSHOT_DIRS:
        target = CLAUDE_DIR / directory
        if target.exists():
            count = _inventory_file_count(target, export_filter)
            lines.append(f"{directory:<10} : {count} file(s)")
        else:
            lines.append(f"{directory:<10} : (empty)")

    print("\n".join(lines))


def cmd_merge(path_a: str, path_b: str):
    """
    Smart-merge two config snapshots.

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

    merged_files, merge_log = _merge_snapshot_files(
        snap_a.get("files", {}), snap_b.get("files", {})
    )

    result = {
        "machine_id": f"merged-{snap_a['machine_id']}-{snap_b['machine_id']}",
        "hostname": "merged",
        "platform": platform.system(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "files": merged_files,
        "merge_log": merge_log,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_consolidate(repo_path: str):
    """Fold all machine snapshots (+ existing consolidated) into consolidated/snapshot.json.

    Merge order is ascending `timestamp`, so the most recent snapshot is applied
    last and its scalars win — recency decides, not filename sort order. Runs the
    whole fold in-process, replacing the SKILL's predictable-/tmp fold-loop.
    """
    repo = Path(repo_path)
    consolidated_path = repo / "consolidated" / "snapshot.json"
    machines_dir = repo / "machines"

    snapshots = []
    if machines_dir.exists():
        for snapshot_file in sorted(machines_dir.glob("*.json")):
            snapshots.append(json.loads(snapshot_file.read_text(encoding="utf-8")))
    snapshots.sort(key=lambda snapshot: snapshot.get("timestamp", ""))

    if consolidated_path.exists():
        base_files = json.loads(consolidated_path.read_text(encoding="utf-8")).get("files", {})
    else:
        base_files = {}

    budget = _LlmMergeBudget(MAX_LLM_MERGES)
    merge_log = []
    for snapshot in snapshots:
        base_files, log = _merge_snapshot_files(
            base_files, snapshot.get("files", {}), budget=budget
        )
        merge_log.extend(log)

    result = {
        "machine_id": "consolidated",
        "hostname": "consolidated",
        "platform": platform.system(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "files": base_files,
    }
    consolidated_path.parent.mkdir(parents=True, exist_ok=True)
    consolidated_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"consolidated": str(consolidated_path), "machines": len(snapshots)}))


def cmd_backup():
    """
    Export current local config state to a timestamped backup file.
    Prints the backup path so the caller can reference it.
    Safe to call before any destructive operation (sync apply, join, etc).
    """
    backup_dir = CLAUDE_DIR / "config-sync-backups"
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
            if not _is_within(dest, CLAUDE_DIR):
                skipped.append(f"{shared_type}/{rel} (escapes ~/.claude)")
                continue
            if dest.exists():
                # Don't overwrite local customisations — skip silently
                skipped.append(f"{shared_type}/{rel}")
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            installed.append(f"{shared_type}/{rel}")

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


def _collect_scan_warnings() -> list:
    """Scan all exportable files for secret-like content.

    Returns a list of {file, line, match, preview}. Shared by the JSON `scan`
    output and the `scan --gate` UX so the detection lives in exactly one place.
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
        path = CLAUDE_DIR / fname
        if path.exists():
            files_to_scan[fname] = _read(path)

    # Subdirectories
    for directory in SNAPSHOT_DIRS:
        files_to_scan.update(_collect_dir(CLAUDE_DIR, directory))

    for rel, content in files_to_scan.items():
        for lineno, line in enumerate(content.splitlines(), start=1):
            for pattern in scan_patterns:
                if pattern.search(line):
                    # Redact the actual matched value in output
                    warnings.append({
                        "file": rel,
                        "line": lineno,
                        "match": pattern.pattern[:40] + "…",
                        "preview": line.strip()[:80] + ("…" if len(line.strip()) > 80 else ""),
                    })
                    break  # one warning per line is enough

    return warnings


def cmd_scan(*flags):
    """Scan exportable files for secret-like content.

    Default: print JSON {"warnings": [...], "clean": bool}.
    `--gate`: print a human-readable block and exit 2 if anything matched, else 0.
    Both skills call `scan --gate` so the warning gate lives in one place.
    """
    warnings = _collect_scan_warnings()

    if "--gate" in flags:
        if warnings:
            print(f"⚠ Secret scan found {len(warnings)} potential issue(s) in your config files:")
            for warning in warnings:
                print(f"  {warning['file']}:{warning['line']} — {warning['preview']}")
            print("")
            print("Review the files above before pushing.")
            sys.exit(2)
        print("✓ Secret scan clean.")
        sys.exit(0)

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
    for path in sorted(memory_dir.rglob("*.md")):
        memory_files[str(path.relative_to(CLAUDE_DIR))] = _read(path)

    if not memory_files:
        print(json.dumps({"suggestions": []}))
        return

    if os.environ.get(LLM_MERGE_ENV) != "1":
        print(json.dumps({"suggestions": [], "note": "LLM promotion disabled — set CONFIG_SYNC_LLM_MERGE=1 to enable nested claude -p analysis"}))
        return

    if not shutil.which("claude"):
        print(json.dumps({"suggestions": [], "note": "claude CLI not available — LLM promotion analysis skipped"}))
        return

    all_memory = "\n\n---\n\n".join(
        f"[{rel}]\n{content}" for rel, content in memory_files.items()
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


def cmd_migrate():
    """
    Rename legacy open-memory-* paths to config-sync-* (idempotent).

    Handles the rename from the former "open-memory" branding. Only moves a
    path when the legacy one exists and the new one does not, so it is a no-op
    on fresh installs and on machines already migrated. Also renames the repo's
    consolidated/brain.json -> consolidated/snapshot.json and stages it so the
    rename is committed on the next sync.

    Prints JSON: {"migrated": [...], "skipped": [...]}.
    """
    moves = [
        (CLAUDE_DIR / "open-memory-config.json", CONFIG_FILE),
        (CLAUDE_DIR / "open-memory-repo", CONFIG_REPO),
        (CLAUDE_DIR / "open-memory-machine-id", CLAUDE_DIR / "config-sync-machine-id"),
        (CLAUDE_DIR / "open-memory-backups", CLAUDE_DIR / "config-sync-backups"),
    ]

    migrated, skipped = [], []
    for old, new in moves:
        if old.exists() and not new.exists():
            new.parent.mkdir(parents=True, exist_ok=True)
            old.rename(new)
            migrated.append(f"{old.name} -> {new.name}")
        elif old.exists() and new.exists():
            skipped.append(f"{old.name} (both exist — left in place)")

    # Rename the consolidated snapshot inside the repo, if present.
    old_snap = CONFIG_REPO / "consolidated" / "brain.json"
    new_snap = CONFIG_REPO / "consolidated" / "snapshot.json"
    if old_snap.exists() and not new_snap.exists():
        old_snap.rename(new_snap)
        migrated.append("consolidated/brain.json -> consolidated/snapshot.json")
        # Stage the rename so the next sync commits it (best-effort).
        if (CONFIG_REPO / ".git").exists():
            try:
                subprocess.run(["git", "add", "-A"], cwd=CONFIG_REPO,
                               capture_output=True, text=True, timeout=30)
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

    print(json.dumps({"migrated": migrated, "skipped": skipped}))


# ---------------------------------------------------------------------------
# Propagator seam — thin CLI wrappers (logic lives in config_sync_propagators)
# ---------------------------------------------------------------------------

def _sync_context(repo_path):
    """Build a SyncContext injecting the live CLAUDE_DIR + the repo path."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    # Deferred import: config_sync <-> config_sync_propagators is a two-way dependency;
    # keep this call-time so hoisting can't form a circular import (SOLID report M2).
    import config_sync_propagators as propagators
    return propagators, propagators.SyncContext(claude_dir=CLAUDE_DIR, repo_dir=Path(repo_path))


def cmd_propagate_export(repo_path):
    propagators, context = _sync_context(repo_path)
    import config_sync_plugins as plugins_module
    results = propagators.run_export(context, plugins_module.export_propagators())
    print(json.dumps({result.propagator: {"written": result.written,
                                           "skipped": result.skipped,
                                           "warnings": result.warnings}
                      for result in results}, indent=2))


def cmd_propagate_apply(repo_path):
    propagators, context = _sync_context(repo_path)
    results = propagators.run_apply(context, propagators.apply_propagators())
    payload = {}
    for result in results:
        payload[result.propagator] = {
            "applied": result.applied,
            "skipped": result.skipped,
            "conflicts": [vars(conflict) for conflict in result.conflicts],
        }
    print(json.dumps(payload, indent=2))


def cmd_resolve_bundle(repo_path, kind, name, winner):
    propagators, context = _sync_context(repo_path)
    propagators.resolve_bundle(context, kind, name, winner)
    print(json.dumps({"resolved": f"{kind}/{name}", "winner": winner}))


def cmd_plugins_plan(repo_path, host=None):
    propagators, context = _sync_context(repo_path)
    import config_sync_plugins as plugins_module
    reader = host if host is not None else plugins_module.ClaudePluginHost(context)
    plan = plugins_module.plan_convergence(context, reader)
    print(json.dumps({
        "actions": [{"verb": action.verb, "target": action.target, "detail": action.detail}
                    for action in plan.actions],
        "skipped": plan.skipped,
    }, indent=2))


def cmd_plugins_apply(repo_path, host=None):
    propagators, context = _sync_context(repo_path)
    import config_sync_plugins as plugins_module
    plugin_host = host if host is not None else plugins_module.ClaudePluginHost(context)
    plan = plugins_module.plan_convergence(context, plugin_host)
    result = plugins_module.execute_plan(context, plan, plugin_host)
    print(json.dumps({
        "outcomes": [{"verb": outcome.verb, "target": outcome.target,
                      "ok": outcome.ok, "message": outcome.message}
                     for outcome in result.outcomes],
        "skipped": result.skipped,
    }, indent=2))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

COMMANDS = {
    "export": (cmd_export, 0),
    "reconcile": (cmd_reconcile, 0),
    "import": (cmd_import, 1),
    "backup": (cmd_backup, 0),
    "status": (cmd_status, 0),
    "merge": (cmd_merge, 2),
    "consolidate": (cmd_consolidate, 1),
    "propagate-export": (cmd_propagate_export, 1),
    "propagate-apply": (cmd_propagate_apply, 1),
    "resolve-bundle": (cmd_resolve_bundle, 4),
    "plugins-plan": (cmd_plugins_plan, 1),
    "plugins-apply": (cmd_plugins_apply, 1),
    "apply-shared": (cmd_apply_shared, 1),
    "log-sync": (cmd_log_sync, None),   # variadic: repo [action] [summary]
    "scan": (cmd_scan, None),   # variadic: optional --gate flag
    "promote": (cmd_promote, 0),
    "machine-id": (cmd_machine_id, 0),
    "clean-settings": (cmd_clean_settings, 1),
    "migrate": (cmd_migrate, 0),
}


def main():
    args = sys.argv[1:]
    if not args or args[0] not in COMMANDS:
        print(f"Usage: config_sync.py <command> [args]\nCommands: {', '.join(COMMANDS)}", file=sys.stderr)
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
