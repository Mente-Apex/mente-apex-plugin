"""The Propagator seam — substitutable propagation channels for config-sync.

DIP: the sync cycle depends only on the Propagator Protocol; concrete
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


@dataclass
class ApplyResult:
    propagator: str
    applied: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)


@runtime_checkable
class Propagator(Protocol):
    name: str

    def export(self, context: SyncContext) -> ExportResult: ...

    def apply(self, context: SyncContext) -> ApplyResult: ...


def run_export(context: SyncContext, propagators: list) -> list:
    return [propagator.export(context) for propagator in propagators]


def run_apply(context: SyncContext, propagators: list) -> list:
    return [propagator.apply(context) for propagator in propagators]


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


def _payload_files(entry: Path) -> dict:
    """Map {relative_posix_path: bytes} for a bundle source (file or dir)."""
    if entry.is_file():
        return {entry.name: entry.read_bytes()}
    payload = {}
    for file_path in sorted(entry.rglob("*")):
        if file_path.is_file() and file_path.name != MANIFEST_NAME:
            payload[file_path.relative_to(entry).as_posix()] = file_path.read_bytes()
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
            payload = _payload_files(entry)
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
                local_hash = _content_hash(_payload_files(destination))
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
