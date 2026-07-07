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
