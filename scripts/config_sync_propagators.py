"""The Propagator seam — substitutable propagation channels for config-sync.

DIP: the sync cycle depends only on the Exporter / Applier Protocols; concrete
propagators receive an injected SyncContext per call (no module globals);
run_export/run_apply iterate an injected list. See the C1 design spec.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, runtime_checkable

MANIFEST_NAME = "bundle-manifest.json"
BUNDLE_KINDS = {"skill": "skills", "agent": "agents"}  # kind -> ~/.claude subdir

# SnapshotPropagator owns only mergeable config — skills/agents are bundles now.
SNAPSHOT_CONFIG_FILES = ["CLAUDE.md", "settings.json", "keybindings.json"]
SNAPSHOT_CONFIG_DIRS = ["memory", "rules"]
_SKIP_APPLY_PREFIXES = ("skills/", "agents/")


@dataclass(frozen=True)
class SyncContext:
    claude_dir: Path
    repo_dir: Path


@dataclass
class BundleConflict:
    kind: str
    name: str
    local_hash: str
    repo_hash: str
    local_exported_at: str
    repo_exported_at: str


@dataclass
class ExportResult:
    propagator: str
    written: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


@dataclass
class ApplyResult:
    propagator: str
    applied: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)


@runtime_checkable
class Exporter(Protocol):
    """Writes this machine's state into the repo. One reason to change: export format."""
    name: str

    def export(self, context: SyncContext) -> ExportResult: ...


@runtime_checkable
class Applier(Protocol):
    """Idempotently converges LOCAL files from the repo and reports what changed.
    Plugins deliberately do NOT implement this — their apply mutates external
    install state and needs consent, so it lives in a separate plan/execute pair."""
    name: str

    def apply(self, context: SyncContext) -> ApplyResult: ...


def run_export(context: SyncContext, propagators: list) -> list:
    return [propagator.export(context) for propagator in propagators]


def run_apply(context: SyncContext, propagators: list) -> list:
    return [propagator.apply(context) for propagator in propagators]


def resolve_bundle(context: SyncContext, kind: str, name: str, winner: str) -> None:
    """Perform a prompted bundle-conflict resolution.

    winner="repo"  -> overwrite the local skill/agent from the repo bundle.
    winner="local" -> re-export the local entry into the repo bundle (local wins).
    """
    propagator = ContentBundlePropagator()
    if winner == "repo":
        bundle_dir = context.repo_dir / "bundles" / BUNDLE_KINDS[kind] / name
        manifest = _read_manifest(bundle_dir)
        destination = propagator._local_entry_path(context, kind, name, manifest.get("is_dir", True))
        propagator._install(bundle_dir, destination, manifest)
    elif winner == "local":
        entry = context.claude_dir / BUNDLE_KINDS[kind] / name
        payload = _payload_files(entry, propagator._export_filter)
        bundle_dir = context.repo_dir / "bundles" / BUNDLE_KINDS[kind] / name
        propagator._write_bundle(bundle_dir, payload, kind, name, entry.is_dir(),
                                 _content_hash(payload), context)
    else:
        raise ValueError(f"winner must be 'local' or 'repo', got {winner!r}")


# ---------------------------------------------------------------------------
# Bundle export filter — which files of a skill/agent source belong in a bundle
# ---------------------------------------------------------------------------

@runtime_checkable
class BundleExportFilter(Protocol):
    """Decides whether a file — addressed by its bundle-relative POSIX path —
    belongs in a synced skill/agent bundle. One reason to change: the exclusion
    policy. Injected into ContentBundlePropagator so the policy is substitutable
    and the copy loop stays closed for modification (OCP)."""

    def should_include(self, relative_path: str) -> bool: ...


class DefaultBundleExportFilter:
    """Excludes vendored / build / scratch artefacts that pollute skill bundles:
    virtualenvs, bytecode caches, VCS metadata, node_modules, packaging dirs.
    A skill's *authored* content (SKILL.md, references/, scripts/*.py) travels; a
    virtualenv left inside the skill dir does not — that was the #44 bloat."""

    #: a path segment equal to any of these excludes the file
    EXCLUDED_SEGMENTS = frozenset({
        "venv", ".venv", "__pycache__", ".git", "node_modules",
        ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".ipynb_checkpoints",
    })
    #: a path segment ending in any of these (packaging metadata dirs) excludes it
    EXCLUDED_SEGMENT_SUFFIXES = (".dist-info", ".egg-info")
    #: a file ending in any of these (compiled bytecode) is excluded
    EXCLUDED_FILE_SUFFIXES = (".pyc", ".pyo")

    def should_include(self, relative_path: str) -> bool:
        segments = relative_path.split("/")
        if any(segment in self.EXCLUDED_SEGMENTS for segment in segments):
            return False
        if any(segment.endswith(self.EXCLUDED_SEGMENT_SUFFIXES) for segment in segments):
            return False
        if relative_path.endswith(self.EXCLUDED_FILE_SUFFIXES):
            return False
        return True


# ---------------------------------------------------------------------------
# Bundle helpers (content-hashed, file-or-dir aware)
# ---------------------------------------------------------------------------

def _machine_id(context: SyncContext) -> str:
    """Stable machine id, injected via context (mirrors config_sync._machine_id)."""
    id_file = context.claude_dir / "config-sync-machine-id"
    if id_file.exists():
        return id_file.read_text().strip()
    import platform
    import uuid
    machine_id = f"{platform.node()}-{uuid.uuid4().hex[:8]}"
    id_file.parent.mkdir(parents=True, exist_ok=True)
    id_file.write_text(machine_id)
    return machine_id


def _payload_files(entry: Path, export_filter: "BundleExportFilter | None" = None) -> dict:
    """Map {relative_posix_path: bytes} for a bundle source (file or dir).

    When an export_filter is supplied, files it rejects (vendored venvs, bytecode,
    …) are omitted — so they neither travel in the bundle nor affect the content
    hash. Export and apply pass the SAME filter, so a skill whose only local
    difference is scratch hashes identically on both sides and raises no false
    conflict (see ContentBundlePropagator.apply)."""
    if entry.is_file():
        return {entry.name: entry.read_bytes()}
    payload = {}
    for file_path in sorted(entry.rglob("*")):
        if not (file_path.is_file() and file_path.name != MANIFEST_NAME):
            continue
        relative_path = file_path.relative_to(entry).as_posix()
        if export_filter is not None and not export_filter.should_include(relative_path):
            continue
        payload[relative_path] = file_path.read_bytes()
    return payload


def _content_hash(payload: dict) -> str:
    hasher = hashlib.sha256()
    for relative_path in sorted(payload):
        hasher.update(relative_path.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(payload[relative_path])
        hasher.update(b"\0")
    return hasher.hexdigest()


def _read_manifest(bundle_dir: Path) -> dict:
    manifest_path = bundle_dir / MANIFEST_NAME
    if not manifest_path.exists():
        return {}
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


class ContentBundlePropagator:
    """Propagates ~/.claude/skills and ~/.claude/agents as atomic, hash-gated bundles.

    Every file travels (fixes PS2); export/apply gate on content hash, not
    presence (fixes PS3, D8). Divergent bundles surface as conflicts rather than
    silently overwriting.
    """

    name = "content-bundle"

    def __init__(self, export_filter: "BundleExportFilter | None" = None):
        # DIP: the exclusion policy is an injected collaborator. Default to the
        # production filter, but the constructor is the seam — tests and future
        # callers substitute their own without touching the copy/hash logic.
        self._export_filter = export_filter if export_filter is not None else DefaultBundleExportFilter()

    def _sources(self, context: SyncContext):
        for kind, subdir in BUNDLE_KINDS.items():
            root = context.claude_dir / subdir
            if not root.exists():
                continue
            for entry in sorted(root.iterdir()):
                if entry.name == MANIFEST_NAME:
                    continue
                yield kind, entry

    def export(self, context: SyncContext) -> ExportResult:
        result = ExportResult(self.name)
        for kind, entry in self._sources(context):
            name = entry.name
            payload = _payload_files(entry, self._export_filter)
            local_hash = _content_hash(payload)
            bundle_dir = context.repo_dir / "bundles" / BUNDLE_KINDS[kind] / name
            if _read_manifest(bundle_dir).get("content_hash") == local_hash:
                result.skipped.append(f"{kind}/{name}")
                continue
            self._write_bundle(bundle_dir, payload, kind, name, entry.is_dir(), local_hash, context)
            result.written.append(f"{kind}/{name}")
        return result

    def _write_bundle(self, bundle_dir, payload, kind, name, is_dir, content_hash, context):
        import shutil
        if bundle_dir.exists():
            shutil.rmtree(bundle_dir)
        for relative_path, content in payload.items():
            target = bundle_dir / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        manifest = {
            "name": name,
            "kind": kind,
            "is_dir": is_dir,
            "content_hash": content_hash,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "machine_id": _machine_id(context),
        }
        bundle_dir.mkdir(parents=True, exist_ok=True)
        (bundle_dir / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def _local_entry_path(self, context, kind, name, is_dir):
        return context.claude_dir / BUNDLE_KINDS[kind] / name

    def apply(self, context: SyncContext) -> ApplyResult:
        import config_sync
        result = ApplyResult(self.name)
        for kind, subdir in BUNDLE_KINDS.items():
            bundles_root = context.repo_dir / "bundles" / subdir
            if not bundles_root.exists():
                continue
            for bundle_dir in sorted(bundles_root.iterdir()):
                if not bundle_dir.is_dir():
                    continue
                manifest = _read_manifest(bundle_dir)
                name = manifest.get("name", bundle_dir.name)
                repo_hash = manifest.get("content_hash")
                destination = self._local_entry_path(context, kind, name, manifest.get("is_dir", True))
                if not config_sync._is_within(destination, context.claude_dir):
                    result.skipped.append(f"{kind}/{name} (escapes ~/.claude)")
                    continue
                if not destination.exists():
                    self._install(bundle_dir, destination, manifest)
                    result.applied.append(f"{kind}/{name}")
                    continue
                local_hash = _content_hash(_payload_files(destination, self._export_filter))
                if local_hash == repo_hash:
                    result.skipped.append(f"{kind}/{name}")
                    continue
                result.conflicts.append(BundleConflict(
                    kind=kind, name=name, local_hash=local_hash, repo_hash=repo_hash or "",
                    local_exported_at="", repo_exported_at=manifest.get("exported_at", ""),
                ))
        return result

    def _install(self, bundle_dir, destination, manifest):
        import shutil
        payload = _payload_files(bundle_dir)
        if manifest.get("is_dir", True):
            if destination.exists():
                shutil.rmtree(destination)
            for relative_path, content in payload.items():
                target = destination / relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(next(iter(payload.values())))


class SnapshotPropagator:
    """Propagates the mergeable text config (CLAUDE.md, memory/, rules/, settings,
    keybindings). Skills/agents are deliberately out of scope — they are bundles.
    On apply it defensively skips any legacy skills/agents keys so old snapshots
    go inert (graceful migration)."""

    name = "snapshot"

    def export(self, context: SyncContext) -> ExportResult:
        import platform
        import config_sync
        files = {}
        for filename in SNAPSHOT_CONFIG_FILES:
            path = context.claude_dir / filename
            if not path.exists():
                continue
            if filename == "settings.json":
                files[filename] = config_sync.json.dumps(config_sync._clean_settings(config_sync._read(path)))
            else:
                files[filename] = config_sync._read(path)
        for directory in SNAPSHOT_CONFIG_DIRS:
            files.update(config_sync._collect_dir(context.claude_dir, directory))

        machine_id = _machine_id(context)
        snapshot = {
            "machine_id": machine_id,
            "hostname": platform.node(),
            "platform": platform.system(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "files": files,
        }
        machines_dir = context.repo_dir / "machines"
        machines_dir.mkdir(parents=True, exist_ok=True)
        (machines_dir / f"{machine_id}.json").write_text(
            config_sync.json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
        return ExportResult(self.name, written=[f"machines/{machine_id}.json"])

    def apply(self, context: SyncContext) -> ApplyResult:
        import config_sync
        result = ApplyResult(self.name)
        consolidated = context.repo_dir / "consolidated" / "snapshot.json"
        if not consolidated.exists():
            return result
        files = config_sync.json.loads(consolidated.read_text(encoding="utf-8")).get("files", {})
        for relative_path, content in files.items():
            if relative_path.startswith(_SKIP_APPLY_PREFIXES):
                result.skipped.append(relative_path)
                continue
            destination = context.claude_dir / relative_path
            if not config_sync._is_within(destination, context.claude_dir):
                result.skipped.append(relative_path)
                continue
            outcome = config_sync._apply_snapshot_file(destination, relative_path, content)
            (result.applied if outcome == "applied" else result.skipped).append(relative_path)
        return result


def apply_propagators() -> list:
    """Composition root for the local-file apply sweep (Snapshot + ContentBundle)."""
    return [SnapshotPropagator(), ContentBundlePropagator()]
