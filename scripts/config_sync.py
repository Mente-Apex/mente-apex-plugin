"""
config_sync.py — cross-platform core for Claude config sync.

Syncs your ~/.claude config files (CLAUDE.md, rules/, skills/, agents/,
memory/ files, settings.json) across machines via a private Git repo.
This is NOT the knowledge brain — for capturing/recalling facts use the
`mem` CLI / the mente-apex-memory MCP server (/memory).

All file manipulation lives here so that SKILL.md files stay clean
and nothing breaks across macOS (BSD) vs Linux (GNU) environments.

Invoke through uv, never through the interpreter the OS ships — this module
targets Python 3.14 and stock macOS still answers `python3` with 3.9:

  py() { sh "<plugin-root>/bin/mente-python" "$@"; }

Usage (`py config_sync.py <command>`):
  export               -> print JSON snapshot to stdout
  import <snapshot>    -> apply snapshot to local Claude state
  backup               -> save timestamped backup, print path
  status               -> print human-readable inventory
  merge <a> <b>        -> smart-merge two snapshots, print result
  apply-shared <repo>  -> install shared artifacts from repo shared/ dir
  log-sync <repo> [action] [summary]  -> append sync entry to meta/sync-log.json
  scan                 -> check all exportable files for secret-like content, print JSON report
  promote              -> analyse memory, print promotion suggestions as JSON
  machine-id           -> print or create stable machine ID
  clean-settings <f>   -> strip secrets from settings JSON, print cleaned version
  migrate              -> rename legacy open-memory-* paths to config-sync-* (idempotent)
"""

import contextlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

# The repair side of the wire-hooks channel: diagnoses registered hooks whose
# target has moved or been wired twice, and prunes them behind a consent gate.
import config_sync_hook_doctor

# Pure hook-provisioning core (issue #68): discovers hooks/hooks.json
# declarations under the named roots and diffs/wires them into settings.json.
import config_sync_hooks

# Portable hook-command paths (issue #65): rewrites machine-absolute paths in
# settings.json hook commands to ${TOKEN} sentinels on export and back on import.
import config_sync_roots

# The text/JSON merge engine lives in its own module (SRP extraction). Only the
# three names cmd_merge/cmd_consolidate actually call are imported — anything else
# is reached at config_sync_merge, where the algorithm lives.
from config_sync_merge import (
    LLM_MERGE_ENV,
    _LlmMergeBudget,
    _merge_snapshot_files,
)

if TYPE_CHECKING:
    # Runtime-free import (TYPE_CHECKING is False at import time) so cmd_status can
    # name BundleExportFilter in an annotation without forming the config_sync <->
    # config_sync_propagators import cycle (SOLID M2).
    from config_sync_propagators import BundleExportFilter
    from config_sync_rejections import RejectionPolicy

# ---------------------------------------------------------------------------
# Paths — always derived from $HOME, never hardcoded
# ---------------------------------------------------------------------------
HOME = Path.home()
CLAUDE_DIR = HOME / ".claude"
CONFIG_FILE = CLAUDE_DIR / "config-sync-config.json"
CONFIG_REPO = CLAUDE_DIR / "config-sync-repo"

# The process environment, as a module global for the same reason HOME is one:
# `default_registry` already takes `environ` injected, but the composition root
# below hardwired `os.environ`, so the seam stopped at the module boundary and
# tests could only reach it by mutating the real process environment.
ENVIRON = os.environ

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
    """Write `content` to `path` atomically.

    Temp file in the same directory, then `os.replace`, which is atomic on
    every platform this runs on. A plain `write_text` truncates first, so a
    crash or a full disk between truncate and write leaves a half-written
    file -- and the files this function writes are `settings.json`, the
    machine registry and the consolidated snapshot, where "half-written" means
    the whole network's desired config is gone rather than merely stale.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # Through a symlink, never onto it. `os.replace` on the link path detaches
    # it and leaves a regular file where the link was -- and a dotfiles layout
    # that symlinks `~/.claude/CLAUDE.md` into a repo is exactly the shape
    # `_is_within` was widened to support, so silently breaking it here would
    # contradict that. Resolving first keeps the swap atomic AND keeps the
    # link, because the temp file then lands beside the real target.
    target = Path(os.path.realpath(path)) if path.is_symlink() else path
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp-{os.getpid()}")
    try:
        temporary.write_text(content, encoding="utf-8")
        # A fresh temp file is 0600-ish by umask; carrying the existing mode
        # over stops a 0600 settings.json quietly becoming world-readable, and
        # stops an executable hook script losing its bit.
        if target.exists():
            os.chmod(temporary, stat.S_IMODE(target.stat().st_mode))
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _is_within(path: Path, root: Path) -> bool:
    """True if `path` names a location at or beneath `root`.

    Compared WITHOUT resolving symlinks, then again after resolving. A
    dotfiles layout that symlinks `~/.claude/skills` to `~/repos/my-skills` is
    ordinary, and resolving both sides made every path under it "escape"
    `~/.claude` -- so import refused every skill, silently, while reporting
    success. Yet resolving is exactly what catches a `../` traversal in a
    hand-edited snapshot, which is why the check exists at all.

    Both, therefore, with the lexical check bounded: the RESOLVED check is
    tried first and accepts anything genuinely beneath the real root. The
    lexical fallback then accepts a path that only leaves the root by
    traversing a symlink the operator themselves put inside `~/.claude` --
    every component of which must exist and be one they created.

    An unbounded lexical check was too permissive: `~/.claude/skills`
    symlinked anywhere let a snapshot write to any location on disk, which is
    a wider door than the traversal guard this function exists to be. Requiring
    the escape to happen through an operator-created symlink INSIDE the config
    directory keeps the dotfiles layout working while leaving `../` and
    absolute-path escapes refused, since neither involves such a link.
    """
    resolved = path.resolve()
    root_resolved = root.resolve()
    if resolved == root_resolved or resolved.is_relative_to(root_resolved):
        return True

    lexical = os.path.normpath(str(path))
    lexical_root = os.path.normpath(str(root))
    if not lexical.startswith(lexical_root + os.sep):
        return False
    return _leaves_root_through_a_symlink(Path(lexical), root)


def _leaves_root_through_a_symlink(path: Path, root: Path) -> bool:
    """True when the only reason `path` escapes `root` is a symlink under it.

    Walks the components between `root` and `path` looking for a link. A
    traversal (`../`) normalises away before this is reached and so finds
    none, which is what keeps it refused.
    """
    current = root
    for part in path.relative_to(os.path.normpath(str(root))).parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _safe_dest(rel: str):
    """Resolve `rel` under CLAUDE_DIR; return None if it escapes the tree.

    Guards against `../` traversal and absolute keys (`CLAUDE_DIR / "/abs"`
    discards the left side) in snapshots that were hand-edited or corrupted.
    """
    candidate = CLAUDE_DIR / rel
    return candidate if _is_within(candidate, CLAUDE_DIR) else None


def _root_registry() -> config_sync_roots.RootRegistry:
    """This machine's root registry: HOME plus CONFIG_SYNC_ROOT_* declarations.
    Built from the live globals so tests that monkeypatch HOME or ENVIRON are
    honoured."""
    return config_sync_roots.default_registry(HOME, ENVIRON)


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
    except json.JSONDecodeError, KeyError:
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
        segments = parts[cache_index + 1 : cache_index + 4]
        if len(segments) == 3:
            marketplace, name, version = segments
    if name is None or marketplace is None:
        key_parts = plugin_key.split("@", 1)
        name = key_parts[0]
        marketplace = key_parts[1] if len(key_parts) > 1 else "unknown"
    if version is None:
        version = entry.get("version", "unknown")

    meta = {
        "key": plugin_key,
        "marketplace": marketplace,
        "name": name,
        "version": version,
    }
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
    """Parse settings JSON and strip any env vars or secret-looking values.

    A file that does not parse is refused, not read as `{}`. This is the same
    defect `ClaudeSettingsHost.read_settings` had, on the write-out side:
    export/push/backup on a machine with a corrupt settings.json wrote
    `"settings.json": "{}"` into the snapshot -- and into the backup that was
    supposed to be the way back -- publishing "this machine has no settings"
    to the whole network.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise config_sync_hooks.CorruptSettingsError(
            f"settings.json is not valid JSON ({exc}); refusing to export it "
            "as empty, because that would publish 'this machine has no "
            "settings' to every other machine. Fix the syntax and retry"
        ) from exc

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

    RECURSIVELY, which is what makes that last sentence true. A top-level
    `merged[key] = value` overlay replaced whole subtrees: a local
    `hooks` block with `PreToolUse` and `SessionStart` entries, overlaid by a
    snapshot carrying only `PreToolUse`, lost `SessionStart` outright -- and
    `permissions.allow` lost every entry this machine had added since its last
    push. That is the ordinary pull path, it runs through `_apply_snapshot_file`
    so `propagate-apply` hits it too, and it did the exact opposite of what
    this docstring promised.
    """
    return _deep_merge(incoming_scrubbed, existing_local)


def _deep_merge(incoming, existing):
    """Union `incoming` onto `existing` without dropping anything from either.

    Three shapes, three rules:

    - dict + dict: merge key by key, recursing. A key only `existing` has
      survives; a key only `incoming` has is added.
    - list + list: `existing` order first, then `incoming` entries not already
      present. Settings lists are sets-with-order in practice
      (`permissions.allow`, `hooks[].hooks`), so a union is what "never
      deletes" means for them; de-duplicated by their JSON encoding, since a
      list of dicts has no hashable identity.
    - anything else: `incoming` wins. A scalar contradiction is a real
      decision, and the network's merged value is the one to take.

    Mismatched types (a key that is a dict locally and a scalar incoming) also
    take `incoming`: there is no union of those, and the snapshot is the more
    recently reconciled of the two.
    """
    if isinstance(incoming, dict) and isinstance(existing, dict):
        merged = dict(existing)
        for key, value in incoming.items():
            merged[key] = (
                _deep_merge(value, existing[key]) if key in existing else value
            )
        return merged
    if isinstance(incoming, list) and isinstance(existing, list):
        return _merge_lists(incoming, existing)
    return incoming


# A list entry that carries one of these is a KEYED RECORD, not an opaque
# value: two entries sharing the key are two versions of one thing and must be
# merged into each other, while a plain scalar or an unkeyed dict is only ever
# itself. `matcher` is the hook block's key -- Claude Code groups hooks by it,
# so `{Bash: [protect]}` and `{Bash: [protect, audit]}` are the same group
# gaining a hook. Fingerprinting whole entries made them two groups, both kept,
# and `protect` then ran twice on every matching call.
_LIST_ENTRY_KEYS = ("matcher",)


def _entry_key(entry):
    """The identity of a list entry, or None when it has none."""
    if not isinstance(entry, dict):
        return None
    for key in _LIST_ENTRY_KEYS:
        if key in entry:
            return (key, json.dumps(entry[key], sort_keys=True))
    return None


def _fingerprint(entry):
    """A value-identity for an unkeyed entry, or None when it has no stable one.

    `json.dumps` raises on anything it cannot serialise (a set, a custom
    object), and letting that escape would abort the entire settings merge over
    one odd entry in one list. None means "cannot compare", and an
    incomparable entry is simply appended rather than deduplicated.
    """
    try:
        return json.dumps(entry, sort_keys=True)
    except TypeError:
        return None


def _merge_lists(incoming, existing):
    """Union two lists, merging entries that share an identity key.

    Order is `existing` first, then whatever `incoming` adds -- so a machine's
    own ordering is preserved and the result is stable across repeated pulls.
    """
    merged = list(existing)
    positions = {}
    seen = set()
    for index, entry in enumerate(existing):
        key = _entry_key(entry)
        if key is not None:
            positions.setdefault(key, index)
        else:
            fingerprint = _fingerprint(entry)
            if fingerprint is not None:
                seen.add(fingerprint)

    for entry in incoming:
        key = _entry_key(entry)
        if key is not None:
            if key in positions:
                index = positions[key]
                merged[index] = _deep_merge(entry, merged[index])
            else:
                positions[key] = len(merged)
                merged.append(entry)
            continue
        fingerprint = _fingerprint(entry)
        if fingerprint is None or fingerprint not in seen:
            if fingerprint is not None:
                seen.add(fingerprint)
            merged.append(entry)
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
                cleaned, _orphans = _reconcile_plugins(
                    cleaned
                )  # in-memory only for the snapshot
                cleaned = _root_registry().portabilize_settings(
                    cleaned
                )  # portable hook paths
                files[fname] = json.dumps(cleaned)
            else:
                files[fname] = _read(path)

    # Subdirectories
    for directory in SNAPSHOT_DIRS:
        files.update(_collect_dir(CLAUDE_DIR, directory))

    # Strip anything that should never leave this machine
    files = {
        rel: content
        for rel, content in files.items()
        if not any(rel.startswith(prefix) for prefix in SNAPSHOT_EXCLUDE_PREFIXES)
    }

    snapshot = {
        "machine_id": _machine_id(),
        "hostname": platform.node(),
        "platform": platform.system(),
        "timestamp": datetime.now(UTC).isoformat(),
        # The token names this machine could have minted while portabilizing.
        # The exporting machine is the only party that knows which `${...}` in
        # a hook command it put there; without this record the importing side
        # cannot tell a config-sync root sentinel from `${CLAUDE_PROJECT_DIR}`
        # or a plain shell variable. See `RootRegistry.unresolved_tokens`.
        "root_tokens": _root_registry().token_names(),
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
    print(
        json.dumps(
            {
                "orphaned_plugins_removed": orphans,
                "stale_cache_dirs_removed": stale_cache,
            }
        )
    )


def _warn_unresolvable_hook(description: str) -> None:
    """Tell the operator a hook was dropped, on stderr.

    stderr, not stdout: every command in this module prints a JSON payload the
    skill parses, and a warning mixed into it would break that parse.
    """
    print(f"config-sync: {description}", file=sys.stderr)


def _drop_unresolvable_hooks(settings: dict, registry, minted_tokens=()) -> tuple:
    """Remove hooks carrying a config-sync root token this machine lacks.

    Returns `(settings, dropped_descriptions)`. The settings dict is rebuilt
    rather than mutated, so a caller's copy is untouched, and a matcher group
    left with no hooks is removed along with its now-empty event list -- an
    empty group is not a neutral leftover, Claude Code reads it as a declared
    matcher that never fires.

    `minted_tokens` comes from the snapshot's `root_tokens`; only a token the
    exporting machine says it minted is treated as ours. A snapshot written
    before that field existed carries none, so nothing is dropped and the
    behaviour degrades to "write it and warn" -- the safe direction, since the
    alternative is deleting a hook that was working.

    Every level is shape-checked. A hand-edited or corrupted snapshot is the
    stated threat model for `_safe_dest`, and this function used to meet one
    with `AttributeError: 'str' object has no attribute 'get'`, aborting the
    whole import on a traceback.
    """
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return settings, []

    result = dict(settings)
    surviving_events = {}
    dropped = []
    for event, matcher_groups in hooks.items():
        if not isinstance(matcher_groups, list):
            surviving_events[event] = matcher_groups
            continue
        surviving_groups = []
        for matcher_group in matcher_groups:
            if not isinstance(matcher_group, dict):
                surviving_groups.append(matcher_group)
                continue
            group_hooks = matcher_group.get("hooks")
            if not isinstance(group_hooks, list):
                surviving_groups.append(matcher_group)
                continue
            surviving_hooks = []
            for hook in group_hooks:
                command = hook.get("command") if isinstance(hook, dict) else None
                unresolved = (
                    registry.unresolved_tokens(command, minted_tokens)
                    if isinstance(command, str)
                    else []
                )
                if unresolved:
                    dropped.append(
                        f"dropped {event} hook {command!r}: this machine "
                        f"declares no root for {', '.join(unresolved)} "
                        f"(set CONFIG_SYNC_ROOT_{unresolved[0]}=<path>)"
                    )
                else:
                    surviving_hooks.append(hook)
            if surviving_hooks:
                surviving_groups.append({**matcher_group, "hooks": surviving_hooks})
        if surviving_groups:
            surviving_events[event] = surviving_groups
    result["hooks"] = surviving_events
    return result, dropped


def _apply_snapshot_file(
    dest: Path, relative_path: str, content: str, minted_tokens=()
) -> str:
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
        registry = _root_registry()
        incoming = registry.localize_settings(incoming)  # portable -> local paths
        # A hook command still carrying a `${TOKEN}` this machine cannot expand
        # is dropped rather than written. The shell expands an undefined
        # variable to nothing, so writing it installs a hook that runs
        # `python3 /hooks/protect.py` and fails on every matching tool call --
        # and the import reported it as `applied`. Dropping it leaves the hook
        # simply absent (visible to `hooks-doctor`) instead of present and
        # broken.
        incoming, dropped = _drop_unresolvable_hooks(incoming, registry, minted_tokens)
        for description in dropped:
            _warn_unresolvable_hook(description)
        local_raw = _read(dest)
        existing_local = json.loads(local_raw) if local_raw.strip() else {}
        merged = json.dumps(
            _merge_import_settings(incoming, existing_local),
            indent=2,
            ensure_ascii=False,
        )
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
    # Absent on a snapshot written before the field existed, which correctly
    # means "nothing is known to be ours", so no hook is dropped.
    minted_tokens = snapshot.get("root_tokens", ())
    applied, skipped = [], []

    for rel, content in files.items():
        if any(rel.startswith(prefix) for prefix in SNAPSHOT_EXCLUDE_PREFIXES):
            skipped.append(rel)
            continue
        dest = _safe_dest(rel)
        if dest is None:
            skipped.append(rel)
            continue
        outcome = _apply_snapshot_file(dest, rel, content, minted_tokens)
        (applied if outcome == "applied" else skipped).append(rel)

    print(json.dumps({"applied": applied, "skipped": skipped}))


def _inventory_file_count(target, export_filter):
    """Count files under `target`, excluding the vendored/build/scratch the export
    filter rejects — so `status` reports a skill/agent's authored files, not a
    virtualenv left inside a skill dir (#44). Uses the SAME filter as the bundle
    export, so the inventory count and what actually syncs agree."""
    return sum(
        1
        for path in target.rglob("*")
        if path.is_file()
        and export_filter.should_include(path.relative_to(target).as_posix())
    )


class RemoteResolver(Protocol):
    """Abstraction over 'what is this repo's remote URL'. cmd_status depends on
    this port, never on git directly, so the subprocess boundary can be faked in
    tests and swapped for a different VCS without touching status-formatting."""

    def resolve(self, repo_path: Path) -> str | None: ...


class GitRemoteResolver:
    """Resolves a repo's origin URL via `git remote get-url origin` — the actual
    source of truth, replacing a `remote` config key that setup never wrote and
    that made status print `unknown` for every user (#48). Returns None when the
    repo is absent or has no origin, so callers render 'not configured'."""

    def resolve(self, repo_path: Path) -> str | None:
        if not repo_path.exists():
            return None
        completed = subprocess.run(
            ["git", "-C", str(repo_path), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            return None
        url = completed.stdout.strip()
        return url or None


def cmd_status(
    remote_resolver: RemoteResolver | None = None,
    export_filter: BundleExportFilter | None = None,
):
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
    lines.append(
        f"config-sync repo : {'✓  ' + str(CONFIG_REPO) if repo_exists else '✗  not initialised'}"
    )

    if config_exists:
        cfg = json.loads(_read(CONFIG_FILE))
        remote_url = remote_resolver.resolve(CONFIG_REPO)
        lines.append(
            f"Remote           : {remote_url if remote_url else 'not configured'}"
        )
        lines.append(f"Last sync        : {cfg.get('last_sync', 'never')}")

    lines.append("")
    lines.append("── Local config inventory ─────────────────────────────")

    claude_md = CLAUDE_DIR / "CLAUDE.md"
    lines.append(
        f"CLAUDE.md  : {'✓ ' + str(len(_read(claude_md).splitlines())) + ' lines' if claude_md.exists() else '✗ missing'}"
    )

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

    # `.get`, like `cmd_consolidate` uses throughout: a snapshot without a
    # `machine_id` raised `KeyError` here AFTER the merge had already
    # succeeded, throwing away completed work over a missing label.
    result = {
        "machine_id": (
            f"merged-{snap_a.get('machine_id', 'unknown')}"
            f"-{snap_b.get('machine_id', 'unknown')}"
        ),
        "hostname": "merged",
        "platform": platform.system(),
        "timestamp": datetime.now(UTC).isoformat(),
        "files": merged_files,
        "merge_log": merge_log,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))


def network_rejection_policy(
    repo_dir: str | Path, machine_id: str = "consolidated"
) -> RejectionPolicy:
    """The policy `cmd_consolidate` uses: network scope ONLY.

    Consolidate writes shared state. A local veto leaking in here would impose
    one machine's private preference on every other machine, so the composite is
    deliberately not used at this call site.

    `machine_id` names the WRITE path only; consolidate never records a
    rejection, so it needs no machine identity and must not touch ~/.claude to
    invent one.
    """
    import config_sync_rejections as rejections_module

    return rejections_module.CompositeRejectionPolicy(
        [rejections_module.SharedRejectionStore(Path(repo_dir), machine_id)]
    )


def cmd_consolidate(repo_path: str, policy: RejectionPolicy | None = None) -> None:
    """Fold all machine snapshots (+ existing consolidated) into consolidated/snapshot.json.

    Merge order is ascending `timestamp`, so the most recent snapshot is applied
    last and its scalars win — recency decides, not filename sort order. Runs the
    whole fold in-process, replacing the SKILL's predictable-/tmp fold-loop.
    """
    import config_sync_rejections as rejections_module

    repo = Path(repo_path)
    consolidated_path = repo / "consolidated" / "snapshot.json"
    machines_dir = repo / "machines"

    if policy is None:
        policy = network_rejection_policy(repo)

    snapshots = []
    if machines_dir.exists():
        for snapshot_file in sorted(machines_dir.glob("*.json")):
            snapshots.append(json.loads(snapshot_file.read_text(encoding="utf-8")))
    snapshots.sort(key=lambda snapshot: snapshot.get("timestamp", ""))

    if consolidated_path.exists():
        base_files = json.loads(consolidated_path.read_text(encoding="utf-8")).get(
            "files", {}
        )
    else:
        base_files = {}

    # The ratchet. `base_files` is the prior consolidated snapshot, which folds
    # its own output back in every run — so content that ever entered it is
    # immortal unless it is filtered HERE, not merely on the way in. Its own
    # timestamp is unknown and older than any live rejection by construction, so
    # the empty string reads as "no fresher intent".
    base_files, base_removed = rejections_module.filter_snapshot_files(
        base_files, policy, ""
    )
    rejected_addresses = list(base_removed)

    budget = _LlmMergeBudget(MAX_LLM_MERGES)
    merge_log = []
    for snapshot in snapshots:
        incoming_files, incoming_removed = rejections_module.filter_snapshot_files(
            snapshot.get("files", {}), policy, snapshot.get("timestamp", "")
        )
        rejected_addresses.extend(incoming_removed)
        base_files, log = _merge_snapshot_files(base_files, incoming_files, budget)
        merge_log.extend(log)

    # `merge_log` is carried into the snapshot AND reported on stdout. It was
    # accumulated and then dropped from both, so a genuine contradiction
    # between two machines got `<<<<<<< Machine A` markers embedded into a live
    # CLAUDE.md by the next apply with no prompt and no warning anywhere. The
    # skill's conflict UX keys off this output; `cmd_merge` already returned it
    # and only `consolidate` -- the command the pull flow actually runs -- did
    # not.
    conflicts = [entry for entry in merge_log if _is_conflict(entry)]
    # The same address can be removed more than once — e.g. carried by the
    # prior consolidated snapshot AND by one or more incoming machine
    # snapshots — so dedupe order-preservingly rather than reporting it once
    # per removal.
    seen_addresses: set[str] = set()
    deduped_rejected_addresses: list[str] = []
    for address in rejected_addresses:
        if address not in seen_addresses:
            seen_addresses.add(address)
            deduped_rejected_addresses.append(address)
    result = {
        "machine_id": "consolidated",
        "hostname": "consolidated",
        "platform": platform.system(),
        "timestamp": datetime.now(UTC).isoformat(),
        "files": base_files,
        "merge_log": merge_log,
        "rejected": deduped_rejected_addresses,
    }
    _write(consolidated_path, json.dumps(result, indent=2, ensure_ascii=False))
    print(
        json.dumps(
            {
                "consolidated": str(consolidated_path),
                "machines": len(snapshots),
                "merge_log": merge_log,
                "conflicts": conflicts,
                "rejected": deduped_rejected_addresses,
            }
        )
    )


class UnknownRejectionTargetError(RuntimeError):
    """A rejection address matches nothing in the consolidated snapshot.

    Refused rather than recorded: a typo'd address would otherwise sit in the
    ledger forever, suppressing nothing and explaining nothing.
    """


class MassRejectionRefusedError(RuntimeError):
    """A rejection would leave a snapshot file with no content at all.

    Refused rather than performed, mirroring `_guard_mass_deletion`: emptying a
    whole file is a *file* rejection, and the operator asked for a section one.
    `--force` says they meant it.
    """


def _consolidated_files(repo_dir):
    path = Path(repo_dir) / "consolidated" / "snapshot.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("files", {})


def _resolve_rejection_address(repo_dir, kind, subject, section_heading, occurrence):
    """The address for `subject`, proven to exist in the consolidated snapshot."""
    import config_sync_merge as merge
    import config_sync_rejections as rejections_module

    files = _consolidated_files(repo_dir)
    if kind == "snapshot-file":
        if subject not in files:
            raise UnknownRejectionTargetError(
                f"no snapshot file {subject!r}; known files: {sorted(files)}"
            )
        return subject
    if kind == "snapshot-section":
        if subject not in files:
            raise UnknownRejectionTargetError(
                f"no snapshot file {subject!r}; known files: {sorted(files)}"
            )
        keys = [key for key, _heading, _body in merge._parse_sections(files[subject])]
        if (section_heading, occurrence) not in keys:
            raise UnknownRejectionTargetError(
                f"no section {section_heading!r} occurrence {occurrence} in "
                f"{subject}; found: {keys}"
            )
        return rejections_module.section_address(subject, section_heading, occurrence)
    raise ValueError(f"kind {kind!r} is not addressable in phase 1")


def _rejection_policy(repo_path):
    """Composition root for the rejection commands: both scopes, since the
    operator chooses per rejection."""
    import config_sync_rejections as rejections_module

    return rejections_module.CompositeRejectionPolicy(
        [
            rejections_module.LocalRejectionStore(
                CLAUDE_DIR / "config-sync-rejections.json"
            ),
            rejections_module.SharedRejectionStore(Path(repo_path), _machine_id()),
        ]
    )


KNOWN_REJECT_OPTIONS = ("--scope", "--section", "--occurrence", "--reason", "--force")

# The one option that takes no value. Kept beside the known-options tuple so the
# parser below never has to guess whether the next token is a value or a flag.
VALUELESS_REJECT_OPTIONS = ("--force",)


def _parse_reject_options(options: list) -> dict:
    """`reject`'s trailing options, refusing anything not in `KNOWN_REJECT_OPTIONS`.

    Fail closed, like `cmd_hooks_prune` does for its own flags: an unrecognised
    option (a typo'd `--scop`) must not silently fall through to a default —
    `--scop local` defaulting `scope` to "network" would propagate a rejection
    meant to stay private to every machine, with a success-shaped JSON payload
    giving no sign anything went wrong.

    Walks flag/value pairs rather than scanning every token for a leading `--`.
    A scan cannot tell a flag from a flag-shaped *value*, so
    `--reason "--needs-follow-up"` was refused as an unknown option — a
    perfectly ordinary reason string that the operator had no way to pass. Only
    a token in flag position is a candidate flag; whatever follows a
    value-taking flag is its value, whatever it looks like.
    """
    parsed: dict = {}
    index = 0
    while index < len(options):
        flag = options[index]
        if flag not in KNOWN_REJECT_OPTIONS:
            raise ValueError(
                f"unknown option {flag!r}; expected one of {KNOWN_REJECT_OPTIONS}"
            )
        if flag in VALUELESS_REJECT_OPTIONS:
            parsed[flag] = True
            index += 1
            continue
        if index + 1 >= len(options):
            raise ValueError(f"option {flag!r} expects a value")
        parsed[flag] = options[index + 1]
        index += 2
    return parsed


def cmd_reject(repo_path, *args):
    """Record a rejection against an address proven to exist in the current
    consolidated snapshot. Refuses a section rejection that would empty its
    whole file, unless `--force` is passed — see `MassRejectionRefusedError`."""
    import config_sync_rejections as rejections_module

    kind = args[0] if args else ""
    if kind not in rejections_module.REJECTION_KINDS:
        raise ValueError(
            f"unknown kind {kind!r}; expected one of {rejections_module.REJECTION_KINDS}"
        )
    subject = args[1]
    options = _parse_reject_options(list(args[2:]))

    scope = options.get("--scope", "network")
    if scope not in rejections_module.REJECTION_SCOPES:
        raise ValueError(f"unknown scope {scope!r}")
    section_heading = options.get("--section")
    occurrence = int(options.get("--occurrence", "0"))
    reason = options.get("--reason", "")
    force = "--force" in options

    address = _resolve_rejection_address(
        repo_path, kind, subject, section_heading, occurrence
    )

    if kind == "snapshot-section" and not force:
        import config_sync_merge as merge

        # Compare rendered content, not heading text: `_parse_sections` always
        # emits a preamble triple (heading `_PREAMBLE`) even for a document with
        # no text before its first heading, so a truthiness check over heading
        # strings never sees an empty remainder — the sentinel itself is
        # non-empty. Rejoining and checking the actual text is what tells us
        # whether anything would survive the rejection.
        #
        # Filtered by the parse KEY `(heading, occurrence)`, not heading text
        # alone: a repeated heading is an explicitly supported document shape
        # (`_parse_sections`'s docstring exists because of it), and dropping
        # every occurrence of a heading that appears twice would falsely
        # refuse a rejection that targets only one of them.
        remaining_sections = [
            triple
            for triple in merge._parse_sections(_consolidated_files(repo_path)[subject])
            if triple[0] != (section_heading, occurrence)
        ]
        remaining_content = rejections_module.rejoin_sections(remaining_sections)
        if not remaining_content.strip():
            raise MassRejectionRefusedError(
                f"rejecting {section_heading!r} would empty {subject}; "
                f"pass --force, or reject the file with kind snapshot-file"
            )

    record = rejections_module.RejectionRecord(
        id=rejections_module.rejection_id_of(kind, address),
        kind=kind,
        address=address,
        scope=scope,
        rejected_at=datetime.now(UTC).isoformat(),
        machine_id=_machine_id(),
        reason=reason,
    )
    _rejection_policy(repo_path).record(record)
    print(json.dumps(vars(record), indent=2, ensure_ascii=False))


def cmd_rejections(repo_path):
    records = _rejection_policy(repo_path).all()
    print(
        json.dumps(
            {"rejections": [vars(record) for record in records]},
            indent=2,
            ensure_ascii=False,
        )
    )


def cmd_unreject(repo_path, rejection_id):
    _rejection_policy(repo_path).forget(rejection_id)
    print(json.dumps({"unrejected": rejection_id}))


def cmd_resolve_rejection(repo_path, rejection_id, decision):
    """Answer another machine's rejection: remove the content here, or keep it.

    `keep` does NOT delete the original — that record lives in the rejecting
    machine's own file and is not ours to edit. It writes our own revival record
    with a newer timestamp, which the composite policy resolves in our favour.

    `remove` is the mirror, and equally a write: it records a LOCAL rejection for
    the same address, so `SnapshotPropagator.apply` withholds the content on this
    machine from the next apply onward. Agreeing by doing nothing would leave the
    consolidated snapshot re-writing the content here on every sync.
    """
    import config_sync_rejections as rejections_module

    if decision not in ("remove", "keep"):
        raise ValueError(f"decision must be 'remove' or 'keep', got {decision!r}")

    policy = _rejection_policy(repo_path)
    original = next((found for found in policy.all() if found.id == rejection_id), None)
    if original is None:
        raise UnknownRejectionTargetError(f"no rejection with id {rejection_id!r}")

    machine_id = _machine_id()
    if decision == "keep":
        revival = rejections_module.RejectionRecord(
            id=rejections_module.rejection_id_of(
                original.kind, original.address + "\0revival"
            ),
            kind=original.kind,
            address=original.address,
            scope="network",
            rejected_at=datetime.now(UTC).isoformat(),
            machine_id=machine_id,
            reason=f"kept on {machine_id}",
            revives=rejection_id,
        )
        policy.record(revival)
    else:
        # The PLAIN target id, not the `\0revival` variant: that is what
        # `CompositeRejectionPolicy.is_rejected` looks for when it asks whether a
        # target is suppressed. It shares the id of the network record being
        # answered, which is harmless and deliberate — scope routing sends this
        # one to the LOCAL store, so it can neither overwrite the rejecting
        # machine's file nor reach the shared repo, and `is_rejected` takes the
        # newest of the matching records, which is this one.
        policy.record(
            rejections_module.RejectionRecord(
                id=rejections_module.rejection_id_of(original.kind, original.address),
                kind=original.kind,
                address=original.address,
                scope="local",
                rejected_at=datetime.now(UTC).isoformat(),
                machine_id=machine_id,
                reason=f"accepted {rejection_id} on {machine_id}",
            )
        )

    print(
        json.dumps(
            {
                "resolved": rejection_id,
                "decision": decision,
                "address": original.address,
            }
        )
    )


# A merged file carries conflict markers when the section union could not
# reconcile two contradictory lines. Detected by the marker the union writes,
# so "was there a conflict?" has one answer rather than one per caller.
CONFLICT_MARKER = "<<<<<<< Machine A"


def _is_conflict(entry) -> bool:
    """True when this merge-log entry records an unresolved contradiction."""
    if isinstance(entry, dict):
        return bool(entry.get("conflict")) or CONFLICT_MARKER in json.dumps(entry)
    return CONFLICT_MARKER in str(entry)


def cmd_backup():
    """
    Export current local config state to a timestamped backup file.
    Prints the backup path so the caller can reference it.
    Safe to call before any destructive operation (sync apply, join, etc).
    """
    backup_dir = CLAUDE_DIR / "config-sync-backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
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
        log = (
            json.loads(log_path.read_text(encoding="utf-8"))
            if log_path.exists()
            else {"syncs": []}
        )
    except json.JSONDecodeError:
        log = {"syncs": []}

    entry = {
        "machine_id": _machine_id(),
        "hostname": platform.node(),
        "timestamp": datetime.now(UTC).isoformat(),
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
        re.compile(r"\b(sk-[A-Za-z0-9]{20,})\b"),  # OpenAI-style keys
        re.compile(r"\b(ghp_[A-Za-z0-9]{36})\b"),  # GitHub tokens
        re.compile(r"\b(xoxb-[0-9]+-[A-Za-z0-9]+)\b"),  # Slack tokens
        re.compile(r"\b(AIza[0-9A-Za-z\-_]{35})\b"),  # Google API keys
        # Generic: key = "long-random-string"
        re.compile(
            r'(?i)(api[_\s]?key|token|secret|password)\s*[=:]\s*["\']?([A-Za-z0-9/+\-_]{20,})["\']?'
        ),
        # AWS-style
        re.compile(r"\b(AKIA[0-9A-Z]{16})\b"),
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
                    warnings.append(
                        {
                            "file": rel,
                            "line": lineno,
                            "match": pattern.pattern[:40] + "…",
                            "preview": line.strip()[:80]
                            + ("…" if len(line.strip()) > 80 else ""),
                        }
                    )
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
            print(
                f"⚠ Secret scan found {len(warnings)} potential issue(s) in your config files:"
            )
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
        print(
            json.dumps(
                {
                    "suggestions": [],
                    "note": "LLM promotion disabled — set CONFIG_SYNC_LLM_MERGE=1 to enable nested claude -p analysis",
                }
            )
        )
        return

    if not shutil.which("claude"):
        print(
            json.dumps(
                {
                    "suggestions": [],
                    "note": "claude CLI not available — LLM promotion analysis skipped",
                }
            )
        )
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
            ["claude", "-p", prompt], capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            # Extract JSON from output (model may add surrounding text)
            output = result.stdout.strip()
            match = re.search(r"\{.*\}", output, re.DOTALL)
            if match:
                print(match.group(0))
                return
    except subprocess.TimeoutExpired, FileNotFoundError:
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
            with contextlib.suppress(subprocess.TimeoutExpired, FileNotFoundError):
                subprocess.run(
                    ["git", "add", "-A"],
                    cwd=CONFIG_REPO,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

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

    return propagators, propagators.SyncContext(
        claude_dir=CLAUDE_DIR, repo_dir=Path(repo_path)
    )


def cmd_propagate_export(repo_path):
    propagators, context = _sync_context(repo_path)
    import config_sync_plugins as plugins_module

    results = propagators.run_export(context, plugins_module.export_propagators())
    print(
        json.dumps(
            {
                result.propagator: {
                    "written": result.written,
                    "skipped": result.skipped,
                    "warnings": result.warnings,
                    "tombstoned": result.tombstoned,
                }
                for result in results
            },
            indent=2,
        )
    )


def cmd_propagate_apply(repo_path):
    propagators, context = _sync_context(repo_path)
    results = propagators.run_apply(context, propagators.apply_propagators(context))
    payload = {}
    for result in results:
        payload[result.propagator] = {
            "applied": result.applied,
            "skipped": result.skipped,
            "conflicts": [vars(conflict) for conflict in result.conflicts],
            "deletions": [vars(deletion) for deletion in result.deletions],
            # Serialised like `conflicts` and `deletions`: the whole record, so
            # Step 4e can name the rejecting machine and the time, pass `id` to
            # `resolve-rejection`, and tell a network tombstone from this
            # machine's own local veto by `scope`.
            "rejection_removals": [
                vars(record) for record in result.rejection_removals
            ],
        }
    print(json.dumps(payload, indent=2))


def cmd_resolve_bundle(repo_path, kind, name, winner):
    propagators, context = _sync_context(repo_path)
    propagators.resolve_bundle(context, kind, name, winner)
    print(json.dumps({"resolved": f"{kind}/{name}", "winner": winner}))


def cmd_resolve_deletion(repo_path, kind, name, decision):
    propagators, context = _sync_context(repo_path)
    propagators.resolve_deletion(context, kind, name, decision)
    print(json.dumps({"resolved": f"{kind}/{name}", "decision": decision}))


def cmd_plugins_plan(repo_path, host=None):
    propagators, context = _sync_context(repo_path)
    import config_sync_plugins as plugins_module

    reader = host if host is not None else plugins_module.ClaudePluginHost(context)
    plan = plugins_module.plan_convergence(context, reader)
    print(
        json.dumps(
            {
                "actions": [
                    {
                        "verb": action.verb,
                        "target": action.target,
                        "detail": action.detail,
                    }
                    for action in plan.actions
                ],
                "skipped": plan.skipped,
            },
            indent=2,
        )
    )


def cmd_plugins_apply(repo_path, host=None):
    propagators, context = _sync_context(repo_path)
    import config_sync_plugins as plugins_module

    plugin_host = host if host is not None else plugins_module.ClaudePluginHost(context)
    plan = plugins_module.plan_convergence(context, plugin_host)
    result = plugins_module.execute_plan(context, plan, plugin_host)
    print(
        json.dumps(
            {
                "outcomes": [
                    {
                        "verb": outcome.verb,
                        "target": outcome.target,
                        "ok": outcome.ok,
                        "message": outcome.message,
                    }
                    for outcome in result.outcomes
                ],
                "skipped": result.skipped,
            },
            indent=2,
        )
    )


def cmd_hooks_plan():
    """Query: what declared hooks are missing from local settings.json."""
    registry = _root_registry()
    declarations = config_sync_hooks.discover_declarations(registry)
    host = config_sync_hooks.ClaudeSettingsHost(CLAUDE_DIR)
    plan = config_sync_hooks.plan_hook_wiring(
        declarations,
        host.read_settings(),
        localize=registry.localize,
        checker=config_sync_hook_doctor.ProbingCommandChecker(
            config_sync_hook_doctor.FilesystemProbe()
        ),
    )
    print(
        json.dumps(
            {
                "actions": [
                    {
                        "verb": action.verb,
                        "hook_id": action.hook_id,
                        "detail": action.detail,
                    }
                    for action in plan.actions
                ],
                "skipped": plan.skipped,
            },
            indent=2,
        )
    )


def cmd_hooks_apply():
    """Gated mutation: register the missing declared hooks (marker-tagged)."""
    registry = _root_registry()
    declarations = config_sync_hooks.discover_declarations(registry)
    host = config_sync_hooks.ClaudeSettingsHost(CLAUDE_DIR)
    # #65/#67 invariant: live settings.json holds localized absolute paths; only
    # the exported snapshot carries ${TOKEN} form. So the declaration is brought
    # into the live file's space before it is compared or written, rather than
    # the file being dragged into the declaration's and pushed back after.
    plan = config_sync_hooks.plan_hook_wiring(
        declarations,
        host.read_settings(),
        localize=registry.localize,
        checker=config_sync_hook_doctor.ProbingCommandChecker(
            config_sync_hook_doctor.FilesystemProbe()
        ),
    )
    result = config_sync_hooks.execute_hook_plan(plan, host)
    print(
        json.dumps(
            {
                "outcomes": [
                    {
                        "hook_id": outcome.hook_id,
                        "ok": outcome.ok,
                        "message": outcome.message,
                    }
                    for outcome in result.outcomes
                ],
                "skipped": result.skipped,
            },
            indent=2,
        )
    )


UNMANAGED_FLAG = "--include-unmanaged"


def _diagnose_live_hooks():
    host = config_sync_hooks.ClaudeSettingsHost(CLAUDE_DIR)
    probe = config_sync_hook_doctor.FilesystemProbe()
    return host, config_sync_hook_doctor.diagnose(host.read_settings(), probe)


def _prune_backup_path():
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return CLAUDE_DIR / f"settings.json.pre-prune-{stamp}"


def _as_report(diagnosis):
    report = {
        "event": diagnosis.site.event,
        "matcher": diagnosis.site.matcher,
        "command": diagnosis.site.command,
        "hook_id": diagnosis.hook_id,
        "managed": diagnosis.managed,
        "findings": list(diagnosis.findings),
    }
    if diagnosis.missing_targets:
        report["missing_targets"] = list(diagnosis.missing_targets)
    if diagnosis.duplicate_of is not None:
        report["duplicate_of"] = diagnosis.duplicate_of.command
    return report


def cmd_hooks_doctor():
    """Query: which hooks in the live settings.json are broken or duplicated.

    Reports every hook, not just config-sync's — a hand-added hook with a dead
    path breaks tool calls just as loudly, and the operator is the only one who
    can decide about it. Shell-fragment commands are counted as unchecked
    rather than listed, since they carry no path to verify.
    """
    _, diagnoses = _diagnose_live_hooks()
    listed = [
        diagnosis
        for diagnosis in diagnoses
        if set(diagnosis.findings) - {config_sync_hook_doctor.OPAQUE}
    ]
    print(
        json.dumps(
            {
                "summary": {
                    "total": len(diagnoses),
                    "healthy": sum(
                        1 for diagnosis in diagnoses if not diagnosis.findings
                    ),
                    "unchecked": sum(
                        1
                        for diagnosis in diagnoses
                        if diagnosis.findings == (config_sync_hook_doctor.OPAQUE,)
                    ),
                    "repairable": sum(
                        1 for diagnosis in diagnoses if diagnosis.repairable
                    ),
                    # What a default `hooks-prune` would actually remove.
                    # `repairable` counts hand-added entries too, which the
                    # default run skips — gating on it promises removals that
                    # never happen.
                    "prunable_by_default": sum(
                        1
                        for diagnosis in diagnoses
                        if diagnosis.prunable(include_unmanaged=False)
                    ),
                },
                "findings": [_as_report(diagnosis) for diagnosis in listed],
            },
            indent=2,
        )
    )


def cmd_hooks_prune(*flags):
    """Gated mutation: remove hooks whose target is gone or exactly duplicated.

    Config-sync's own registrations only, unless the operator passes
    --include-unmanaged. Advisory findings are never acted on.
    """
    unknown = [flag for flag in flags if flag != UNMANAGED_FLAG]
    if unknown:
        print(
            f"Error: unknown flag(s) {' '.join(unknown)}; "
            f"'hooks-prune' accepts only {UNMANAGED_FLAG}",
            file=sys.stderr,
        )
        sys.exit(1)

    live_host, diagnoses = _diagnose_live_hooks()
    plan = config_sync_hook_doctor.plan_hook_pruning(
        diagnoses, include_unmanaged=UNMANAGED_FLAG in flags
    )
    # The only command in config-sync that deletes. It gets a rollback path,
    # written before the first mutation and only when there is one to make.
    host = config_sync_hooks.BackingUpSettingsHost(live_host, _prune_backup_path())
    result = config_sync_hook_doctor.execute_prune_plan(plan, host)
    print(
        json.dumps(
            {
                "removed": [
                    {
                        "command": outcome.command,
                        "ok": outcome.ok,
                        "reason": outcome.message,
                    }
                    for outcome in result.outcomes
                ],
                "skipped": result.skipped,
                "backup": (
                    str(host.backup_path)
                    if any(outcome.ok for outcome in result.outcomes)
                    else None
                ),
            },
            indent=2,
        )
    )


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
    "resolve-deletion": (cmd_resolve_deletion, 4),
    "plugins-plan": (cmd_plugins_plan, 1),
    "plugins-apply": (cmd_plugins_apply, 1),
    "hooks-plan": (cmd_hooks_plan, 0),
    "hooks-apply": (cmd_hooks_apply, 0),
    "hooks-doctor": (cmd_hooks_doctor, 0),
    "hooks-prune": (cmd_hooks_prune, None),  # variadic: optional --include-unmanaged
    "apply-shared": (cmd_apply_shared, 1),
    "log-sync": (cmd_log_sync, None),  # variadic: repo [action] [summary]
    "scan": (cmd_scan, None),  # variadic: optional --gate flag
    "promote": (cmd_promote, 0),
    "machine-id": (cmd_machine_id, 0),
    "clean-settings": (cmd_clean_settings, 1),
    "migrate": (cmd_migrate, 0),
    "reject": (cmd_reject, None),  # variadic: repo kind subject [--scope|--section|...]
    "rejections": (cmd_rejections, 1),
    "unreject": (cmd_unreject, 2),
    "resolve-rejection": (cmd_resolve_rejection, 3),
}


def main():
    args = sys.argv[1:]
    if not args or args[0] not in COMMANDS:
        print(
            f"Usage: config_sync.py <command> [args]\nCommands: {', '.join(COMMANDS)}",
            file=sys.stderr,
        )
        sys.exit(1)

    cmd_name = args[0]
    fn, expected_args = COMMANDS[cmd_name]
    provided = len(args) - 1

    if expected_args is not None and provided != expected_args:
        print(
            f"Error: '{cmd_name}' expects {expected_args} argument(s), got {provided}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Deferred, like every other use of this module here: importing it at
    # module scope reintroduces a circular import.
    import config_sync_plugins
    import config_sync_rejections

    try:
        fn(*args[1:])
    except (
        config_sync_hooks.CorruptSettingsError,
        config_sync_plugins.CorruptPluginStateError,
        config_sync_rejections.CorruptRejectionLedgerError,
        UnknownRejectionTargetError,
        MassRejectionRefusedError,
        # `ValueError` and `IndexError` are how the argument-validating commands
        # already say no, and a variadic command gets no arity check from the
        # table above. `reject <repo> plugin foo@bar` names a kind
        # `REJECTION_KINDS` deliberately lists for phase 2 and dies on
        # `_resolve_rejection_address`'s ValueError; `reject <repo>
        # snapshot-file` with no subject dies on an IndexError; a non-numeric
        # `--occurrence` dies inside `int()`. All three are refusals the
        # operator can act on, and all three exited 1 with a stack trace while
        # every sibling refusal exited 2 with a message.
        ValueError,
        IndexError,
    ) as exc:
        # A named refusal, not a traceback: the operator's settings.json does
        # not parse, and the actionable half of that is the message, not the
        # stack. Exit 2 so a caller can tell "refused to act" from an ordinary
        # failure.
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
