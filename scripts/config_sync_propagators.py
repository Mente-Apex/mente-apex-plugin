"""The Propagator seam — substitutable propagation channels for config-sync.

DIP: the sync cycle depends only on the Exporter / Applier Protocols; concrete
propagators receive an injected SyncContext per call (no module globals);
run_export/run_apply iterate an injected list. See the C1 design spec.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

MANIFEST_NAME = "bundle-manifest.json"
BUNDLE_KINDS = {"skill": "skills", "agent": "agents"}  # kind -> ~/.claude subdir


def _clear_conflicting_type(target) -> None:
    """Make room at `target` when what is there is the wrong KIND of thing.

    A bundle can legitimately turn `docs/` into a file named `docs`, or the
    reverse. `write_bytes` onto an existing directory raises
    `IsADirectoryError`, and `mkdir(parents=True)` through an existing file
    raises `NotADirectoryError` -- both escaping `_install` AFTER the stale
    sweep has already unlinked things, leaving the destination half-applied.
    The old `rmtree(destination)` never hit this because it deleted everything
    first; removing that safety net is what exposed the case.

    Only the exact conflicting path is removed, never a wider tree.
    """
    import shutil

    if target.is_dir() and not target.is_symlink():
        shutil.rmtree(target)
        return
    for ancestor in list(target.parents):
        if ancestor.is_file():
            ancestor.unlink()
            return


def _prune_directories_emptied_by(root, removed_relative_paths) -> None:
    """Remove directories the stale-file sweep emptied, and only those.

    Walks UP from each file the sweep removed, never down from `root`. The
    previous `root.rglob("*")` scan was catastrophically wider than its own
    docstring claimed: it recursed INTO `.git` and `.venv` and rmdir'd every
    empty directory it found there, so `.git/refs/heads`, `.git/objects/pack`
    and `site-packages` were destroyed and `git status` in the skill returned
    "fatal: not a git repository". It also deleted empty directories the user
    had created deliberately, and crashed with `NotADirectoryError` on a
    symlink to an empty directory (`is_dir()` follows the link, `rmdir` does
    not).

    Restricting the walk to the parents of files this sweep actually unlinked
    makes all three impossible by construction: nothing inside an excluded
    tree is ever removed, so nothing inside one is ever a candidate.
    """
    for relative_path in removed_relative_paths:
        directory = (root / relative_path).parent
        while directory != root and directory.is_dir():
            if any(directory.iterdir()):
                break
            try:
                directory.rmdir()
            except OSError:
                # A symlink, a race, a permission problem: leaving a directory
                # in place is always safe, so none of them is worth failing an
                # install that has already written its payload.
                break
            directory = directory.parent


# Deleting everything you previously exported stops rather than propagating.
# Below this many bundles the "whole set" is small enough that a deliberate
# clear-out is as likely as a failed scan, and the guard would be noise.
MASS_DELETE_THRESHOLD = 2
MASS_DELETE_OVERRIDE = "CONFIG_SYNC_ALLOW_MASS_DELETE"

# Module-level so a test can substitute it, matching how config_sync exposes
# its own HOME/ENVIRON seams rather than reading os.environ inline.
ENVIRON = os.environ

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
    tombstoned: list = field(default_factory=list)


@dataclass
class ApplyResult:
    propagator: str
    applied: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)
    deletions: list = field(default_factory=list)
    rejection_removals: list = field(default_factory=list)


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

    Thin module-level entry point delegating to
    ContentBundlePropagator.resolve_conflict, where the logic lives with the class
    whose install/export internals it needs (SOLID N3).
    """
    ContentBundlePropagator().resolve_conflict(context, kind, name, winner)


def resolve_deletion(context: SyncContext, kind: str, name: str, decision: str) -> None:
    """Perform a prompted bundle-deletion resolution.

    decision="remove" -> delete the local skill/agent (the network retired it). The
      repo tombstone stays so other machines also see the deletion.
    decision="keep"   -> leave it. Because the machine still has it, the next export
      re-adds the bundle and supersedes the tombstone (disagreement resolves as
      most-recent-action-wins).
    """
    if decision == "keep":
        return
    if decision != "remove":
        raise ValueError(f"decision must be 'remove' or 'keep', got {decision!r}")
    if kind not in BUNDLE_KINDS:
        raise ValueError(f"unknown bundle kind: {kind!r}")
    import shutil

    # Deferred import: config_sync <-> config_sync_propagators is a two-way dep (SOLID M2).
    import config_sync

    destination = context.claude_dir / BUNDLE_KINDS[kind] / name
    if not config_sync._is_within(destination, context.claude_dir):
        raise ValueError(f"refusing to remove a path escaping ~/.claude: {destination}")
    if destination.is_dir():
        shutil.rmtree(destination)
    elif destination.exists():
        destination.unlink()


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
    EXCLUDED_SEGMENTS = frozenset(
        {
            "venv",
            ".venv",
            "__pycache__",
            ".git",
            "node_modules",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            ".tox",
            ".ipynb_checkpoints",
        }
    )
    #: a path segment ending in any of these (packaging metadata dirs) excludes it
    EXCLUDED_SEGMENT_SUFFIXES = (".dist-info", ".egg-info")
    #: a file ending in any of these (compiled bytecode) is excluded
    EXCLUDED_FILE_SUFFIXES = (".pyc", ".pyo")

    def should_include(self, relative_path: str) -> bool:
        segments = relative_path.split("/")
        if any(segment in self.EXCLUDED_SEGMENTS for segment in segments):
            return False
        if any(
            segment.endswith(self.EXCLUDED_SEGMENT_SUFFIXES) for segment in segments
        ):
            return False
        if relative_path.endswith(self.EXCLUDED_FILE_SUFFIXES):  # noqa: SIM103
            return False
        # Kept as a guard-clause chain rather than `return not ...`: each exclusion
        # rule is one symmetric clause, so adding a fourth is a new line, not a
        # rewrite of the return expression.
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


def _payload_files(
    entry: Path, export_filter: BundleExportFilter | None = None
) -> dict:
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
        if export_filter is not None and not export_filter.should_include(
            relative_path
        ):
            continue
        payload[relative_path] = file_path.read_bytes()
    return payload


#: kind -> required entrypoint filename a bundle payload must carry to be valid.
#: A skill without SKILL.md (or an agent/skill dir reduced to only filtered-out
#: scratch) is broken; exporting it would clobber the last-good bundle network-wide.
_REQUIRED_ENTRYPOINT = {"skill": "SKILL.md"}


def _is_exportable_payload(kind: str, payload: dict) -> bool:
    """True when a bundle payload is safe to export: non-empty and carrying its
    required entrypoint. Guards export against propagating an empty / broken
    skill/agent (#73) — an empty payload must never overwrite a good bundle."""
    if not payload:
        return False
    entrypoint = _REQUIRED_ENTRYPOINT.get(kind)
    return entrypoint is None or entrypoint in payload


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


INDEX_DIRNAME = ".index"
TOMBSTONES_DIRNAME = ".tombstones"


@dataclass(frozen=True)
class Tombstone:
    kind: str
    name: str
    deleted_at: str
    machine_id: str


@dataclass(frozen=True)
class BundleDeletion:
    kind: str
    name: str
    machine_id: str
    deleted_at: str


class BundleDeletionLedger:
    """Deletion bookkeeping for skill/agent bundles, persisted under the repo.

    Two records, both git-tracked and per-file so they converge without merge
    conflicts (the pattern machines/<id>.json already uses):
      - a per-machine export index (what a machine had at its last export), which
        makes deletion *detection* possible;
      - per-bundle tombstones ({kind, name, deleted_at, machine_id}).
    Stateless w.r.t. the repo: repo_dir flows in per call, so one instance serves
    any repo and is trivially faked in tests. One reason to change: the on-disk
    layout of these records.
    """

    def _index_path(self, repo_dir, machine_id):
        return repo_dir / "bundles" / INDEX_DIRNAME / f"{machine_id}.json"

    def _tombstone_path(self, repo_dir, kind, name):
        if "/" in name or "/" in kind:
            raise ValueError(f"bundle kind/name must not contain '/': {kind}/{name}")
        return (
            repo_dir
            / "bundles"
            / TOMBSTONES_DIRNAME
            / BUNDLE_KINDS[kind]
            / f"{name}.json"
        )

    def previously_exported(self, repo_dir, machine_id):
        index_path = self._index_path(repo_dir, machine_id)
        if not index_path.exists():
            return set()
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return set()
        return set(data.get("bundles", []))

    def record_export(self, repo_dir, machine_id, current):
        index_path = self._index_path(repo_dir, machine_id)
        index_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "machine_id": machine_id,
            "updated_at": datetime.now(UTC).isoformat(),
            "bundles": sorted(current),
        }
        index_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def tombstone(self, repo_dir, kind, name, machine_id, when):
        tombstone_path = self._tombstone_path(repo_dir, kind, name)
        tombstone_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "kind": kind,
            "name": name,
            "deleted_at": when,
            "machine_id": machine_id,
        }
        tombstone_path.write_text(json.dumps(record, indent=2), encoding="utf-8")

    def clear_tombstone(self, repo_dir, kind, name):
        tombstone_path = self._tombstone_path(repo_dir, kind, name)
        if tombstone_path.exists():
            tombstone_path.unlink()

    def tombstone_for(self, repo_dir, kind, name):
        tombstone_path = self._tombstone_path(repo_dir, kind, name)
        if not tombstone_path.exists():
            return None
        data = json.loads(tombstone_path.read_text(encoding="utf-8"))
        return Tombstone(
            kind=data["kind"],
            name=data["name"],
            deleted_at=data["deleted_at"],
            machine_id=data["machine_id"],
        )

    def tombstones(self, repo_dir):
        root = repo_dir / "bundles" / TOMBSTONES_DIRNAME
        collected = []
        if not root.exists():
            return collected
        # The kind is read back from each tombstone's own payload, so only the
        # directory name is needed to walk them.
        for subdir in BUNDLE_KINDS.values():
            subdir_path = root / subdir
            if not subdir_path.exists():
                continue
            for tombstone_file in sorted(subdir_path.glob("*.json")):
                data = json.loads(tombstone_file.read_text(encoding="utf-8"))
                collected.append(
                    Tombstone(
                        kind=data["kind"],
                        name=data["name"],
                        deleted_at=data["deleted_at"],
                        machine_id=data["machine_id"],
                    )
                )
        return collected

    def is_deleted(self, repo_dir, kind, name, bundle_exported_at):
        tombstone = self.tombstone_for(repo_dir, kind, name)
        if tombstone is None:
            return False
        return tombstone.deleted_at > (bundle_exported_at or "")


class ContentBundlePropagator:
    """Propagates ~/.claude/skills and ~/.claude/agents as atomic, hash-gated bundles.

    Every file travels (fixes PS2); export/apply gate on content hash, not
    presence (fixes PS3, D8). Divergent bundles surface as conflicts rather than
    silently overwriting.
    """

    name = "content-bundle"

    def __init__(self, export_filter: BundleExportFilter | None = None, ledger=None):
        # DIP: both the exclusion policy and the deletion ledger are injected
        # collaborators. Defaults are the production implementations; the
        # constructor is the seam tests substitute through.
        self._export_filter = (
            export_filter if export_filter is not None else DefaultBundleExportFilter()
        )
        self._ledger = ledger if ledger is not None else BundleDeletionLedger()

    def _sources(self, context: SyncContext):
        for kind, subdir in BUNDLE_KINDS.items():
            root = context.claude_dir / subdir
            if not root.exists():
                continue
            for entry in sorted(root.iterdir()):
                if entry.name == MANIFEST_NAME:
                    continue
                yield kind, entry

    def _scanned_kinds(self, context: SyncContext) -> set:
        """The bundle kinds whose source directory actually exists right now.

        `_sources` yields nothing for a kind whose root is absent, which is
        indistinguishable from a kind whose root is present and empty -- and
        the deletion pass read that silence as "the user deleted all of these".
        A `~/.claude/skills` symlinked to an unmounted external volume, or
        renamed mid-migration, therefore tombstoned and `rmtree`d every skill
        bundle in the repo and proposed the deletion to every other machine.

        Only a kind that was actually scanned can contribute deletions.
        """
        return {
            kind
            for kind, subdir in BUNDLE_KINDS.items()
            if (context.claude_dir / subdir).exists()
        }

    @staticmethod
    def _guard_mass_deletion(candidates: set, previously_exported: set, result) -> set:
        """Refuse to tombstone an entire KIND's previous export in one run.

        Deleting every skill you have is a real thing an operator may do, but
        it is far likelier to be a scan that went wrong in a way
        `_scanned_kinds` does not cover -- a permission error part-way through,
        a directory emptied by a failed move. The blast radius is the whole
        network: every other machine is then offered the same deletion.

        Per kind, because comparing against the whole previous export meant a
        single surviving bundle of ANY kind disarmed the guard: five skills
        emptied by a failed move went through untouched as long as one agent
        remained. Each kind is judged against its own previous export, and a
        refusal for one kind does not block deletions in another.

        A partial deletion within a kind (the ordinary case) is unaffected.
        """
        if not candidates:
            return candidates
        if ENVIRON.get(MASS_DELETE_OVERRIDE) == "1":
            return candidates

        allowed = set()
        for kind in sorted(BUNDLE_KINDS):
            prefix = f"{kind}/"
            previous_of_kind = {
                key for key in previously_exported if key.startswith(prefix)
            }
            candidates_of_kind = {key for key in candidates if key.startswith(prefix)}
            if not candidates_of_kind:
                continue
            wipes_the_kind = candidates_of_kind == previous_of_kind
            if wipes_the_kind and len(previous_of_kind) >= MASS_DELETE_THRESHOLD:
                result.warnings.append(
                    f"REFUSED to tombstone all {len(candidates_of_kind)} "
                    f"previously-exported {BUNDLE_KINDS[kind]} at once: a "
                    "whole-set disappearance is far more often a failed scan "
                    "than a deliberate deletion, and this would propose the "
                    "same deletion to every other machine. Nothing of this "
                    "kind was deleted. If you really did remove them all, "
                    f"re-run with {MASS_DELETE_OVERRIDE}=1."
                )
                continue
            allowed |= candidates_of_kind
        return allowed

    def export(self, context: SyncContext) -> ExportResult:
        result = ExportResult(self.name)
        machine_id = _machine_id(context)
        current = {f"{kind}/{entry.name}" for kind, entry in self._sources(context)}
        previously_exported = self._ledger.previously_exported(
            context.repo_dir, machine_id
        )
        deleted_at = datetime.now(UTC).isoformat()

        # Deletions: bundles this machine used to have and no longer does.
        import shutil

        scanned_kinds = self._scanned_kinds(context)
        candidates = set()
        for deleted_key in previously_exported - current:
            deleted_kind = deleted_key.split("/", 1)[0]
            if deleted_kind not in scanned_kinds:
                result.warnings.append(
                    f"{deleted_key}: NOT tombstoned — the "
                    f"{BUNDLE_KINDS.get(deleted_kind, deleted_kind)} directory "
                    "does not exist on this machine, so its absence is not "
                    "evidence of a deletion (an unmounted volume or a "
                    "half-finished move looks identical)"
                )
                continue
            candidates.add(deleted_key)

        candidates = self._guard_mass_deletion(candidates, previously_exported, result)

        for deleted_key in sorted(candidates):
            deleted_kind, deleted_name = deleted_key.split("/", 1)
            self._ledger.tombstone(
                context.repo_dir, deleted_kind, deleted_name, machine_id, deleted_at
            )
            stale_bundle = (
                context.repo_dir / "bundles" / BUNDLE_KINDS[deleted_kind] / deleted_name
            )
            if stale_bundle.exists():
                shutil.rmtree(stale_bundle)
            result.tombstoned.append(deleted_key)

        for kind, entry in self._sources(context):
            name = entry.name
            # A locally-present bundle supersedes any tombstone for it (deliberate re-add),
            # but only if the tombstone predates THIS export's timestamp. A tombstone
            # dated at or after `deleted_at` is a FUTURE-dated tombstone from this
            # machine's point of view — e.g. another machine with a clock ahead of this
            # one, or a deletion that genuinely happened later than this sync — and must
            # be preserved rather than clobbered just because this run still finds the
            # bundle present locally.
            existing_tombstone = self._ledger.tombstone_for(
                context.repo_dir, kind, name
            )
            payload = _payload_files(entry, self._export_filter)
            if not _is_exportable_payload(kind, payload):
                # Empty or entrypoint-less source: leave the last-good bundle intact
                # and do NOT tombstone it — there is simply nothing valid to export.
                #
                # And do NOT clear an existing tombstone either, which is why
                # the clear now happens BELOW this gate rather than above it.
                # Clearing first silently reverted another machine's deliberate
                # deletion: the tombstone went, no bundle was written in its
                # place, and a third machine that had not yet applied saw
                # neither -- so it never proposed the deletion, re-published
                # the bundle on its next export, and the deletion was undone
                # with nobody consenting to it. The documented "keep" path
                # requires a user decision; this path took it without asking.
                result.warnings.append(
                    f"{kind}/{name}: skipped — empty or missing entrypoint "
                    f"({_REQUIRED_ENTRYPOINT.get(kind, 'content')}); last-good bundle preserved"
                )
                continue
            # A locally-present, EXPORTABLE bundle supersedes a tombstone for
            # it (a deliberate re-add), but only one that predates this run --
            # see the comment above the tombstone read.
            if (
                existing_tombstone is not None
                and existing_tombstone.deleted_at < deleted_at
            ):
                self._ledger.clear_tombstone(context.repo_dir, kind, name)
            local_hash = _content_hash(payload)
            bundle_dir = context.repo_dir / "bundles" / BUNDLE_KINDS[kind] / name
            if _read_manifest(bundle_dir).get("content_hash") == local_hash:
                result.skipped.append(f"{kind}/{name}")
                continue
            self._write_bundle(
                bundle_dir, payload, kind, name, entry.is_dir(), local_hash, context
            )
            result.written.append(f"{kind}/{name}")

        # Anything this run declined to tombstone stays in the index. Recording
        # the reduced `current` made the refusal one-shot: the guard warned
        # once, the machine then forgot it had ever exported those bundles, and
        # the very override the warning tells the operator to use had nothing
        # left to act on. The same amnesia silently disarmed `_scanned_kinds`
        # -- an unmounted volume warned on the first run and never again.
        retained = previously_exported - set(result.tombstoned)
        self._ledger.record_export(context.repo_dir, machine_id, current | retained)
        return result

    def _write_bundle(
        self, bundle_dir, payload, kind, name, is_dir, content_hash, context
    ):
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
            "exported_at": datetime.now(UTC).isoformat(),
            "machine_id": _machine_id(context),
        }
        bundle_dir.mkdir(parents=True, exist_ok=True)
        (bundle_dir / MANIFEST_NAME).write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )

    def _local_entry_path(self, context, kind, name, is_dir):
        return context.claude_dir / BUNDLE_KINDS[kind] / name

    def apply(self, context: SyncContext) -> ApplyResult:
        # Deferred: config_sync_propagators <-> config_sync is a two-way dependency;
        # keep this call-time (hoisting reintroduces a circular import — SOLID M2).
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
                destination = self._local_entry_path(
                    context, kind, name, manifest.get("is_dir", True)
                )
                if not config_sync._is_within(destination, context.claude_dir):
                    result.skipped.append(f"{kind}/{name} (escapes ~/.claude)")
                    continue
                if not destination.exists():
                    if self._ledger.is_deleted(
                        context.repo_dir, kind, name, manifest.get("exported_at", "")
                    ):
                        result.skipped.append(f"{kind}/{name} (tombstoned)")
                        continue
                    self._install(bundle_dir, destination, manifest)
                    result.applied.append(f"{kind}/{name}")
                    continue
                local_hash = _content_hash(
                    _payload_files(destination, self._export_filter)
                )
                if local_hash == repo_hash:
                    result.skipped.append(f"{kind}/{name}")
                    continue
                if self._ledger.is_deleted(
                    context.repo_dir, kind, name, manifest.get("exported_at", "")
                ):
                    result.skipped.append(f"{kind}/{name} (tombstoned)")
                    continue
                result.conflicts.append(
                    BundleConflict(
                        kind=kind,
                        name=name,
                        local_hash=local_hash,
                        repo_hash=repo_hash or "",
                        local_exported_at="",
                        repo_exported_at=manifest.get("exported_at", ""),
                    )
                )

        # Propose local removals for bundles the network has retired but this
        # machine still has. Nothing is removed here — resolve-deletion does that
        # after consent.
        for tombstone in self._ledger.tombstones(context.repo_dir):
            destination = self._local_entry_path(
                context, tombstone.kind, tombstone.name, True
            )
            if not destination.exists():
                continue
            repo_bundle = (
                context.repo_dir
                / "bundles"
                / BUNDLE_KINDS[tombstone.kind]
                / tombstone.name
            )
            bundle_exported_at = _read_manifest(repo_bundle).get("exported_at", "")
            if self._ledger.is_deleted(
                context.repo_dir, tombstone.kind, tombstone.name, bundle_exported_at
            ):
                result.deletions.append(
                    BundleDeletion(
                        kind=tombstone.kind,
                        name=tombstone.name,
                        machine_id=tombstone.machine_id,
                        deleted_at=tombstone.deleted_at,
                    )
                )
        return result

    def _install(self, bundle_dir, destination, manifest):
        """Write a bundle's payload into `destination`.

        Replaces only what the bundle is entitled to replace. The old
        `rmtree(destination)` deleted everything and repopulated from a payload
        that, by the export filter's design, never contains `.git`, `.venv`,
        `node_modules` or `__pycache__` -- so resolving a conflict in the
        repo's favour destroyed the local skill's own git checkout and
        virtualenv, unrecoverably. The filter's contract is "this content does
        not travel", not "this content may be deleted".

        So: files the bundle carries are written, files the destination has
        that the bundle does not are removed ONLY when the filter says they
        would have travelled, and everything the filter excludes is left
        exactly where it is.
        """
        payload = _payload_files(bundle_dir)
        if not manifest.get("is_dir", True):
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(next(iter(payload.values())))
            return

        # Stale payload files: present locally, exportable, and absent from the
        # bundle. Computed through the same filter the export used, so the two
        # sides agree on what "the bundle's content" means.
        existing_exportable = set(_payload_files(destination, self._export_filter))
        removed = sorted(existing_exportable - set(payload))
        for relative_path in removed:
            (destination / relative_path).unlink(missing_ok=True)

        for relative_path, content in payload.items():
            target = destination / relative_path
            _clear_conflicting_type(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)

        _prune_directories_emptied_by(destination, removed)

    def resolve_conflict(
        self, context: SyncContext, kind: str, name: str, winner: str
    ) -> None:
        """Apply a prompted bundle-conflict resolution using this propagator's own
        install/export internals.

        winner="repo"  -> overwrite the local skill/agent from the repo bundle.
        winner="local" -> re-export the local entry into the repo bundle (local wins).
        """
        if winner == "repo":
            bundle_dir = context.repo_dir / "bundles" / BUNDLE_KINDS[kind] / name
            manifest = _read_manifest(bundle_dir)
            destination = self._local_entry_path(
                context, kind, name, manifest.get("is_dir", True)
            )
            self._install(bundle_dir, destination, manifest)
        elif winner == "local":
            entry = context.claude_dir / BUNDLE_KINDS[kind] / name
            payload = _payload_files(entry, self._export_filter)
            bundle_dir = context.repo_dir / "bundles" / BUNDLE_KINDS[kind] / name
            self._write_bundle(
                bundle_dir,
                payload,
                kind,
                name,
                entry.is_dir(),
                _content_hash(payload),
                context,
            )
        else:
            raise ValueError(f"winner must be 'local' or 'repo', got {winner!r}")


class SnapshotPropagator:
    """Propagates the mergeable text config (CLAUDE.md, memory/, rules/, settings,
    keybindings). Skills/agents are deliberately out of scope — they are bundles.
    On apply it defensively skips any legacy skills/agents keys so old snapshots
    go inert (graceful migration)."""

    name = "snapshot"

    def __init__(self, policy=None):
        # Deferred: sibling script, not a package.
        import config_sync_rejections as rejections_module

        self._policy = (
            policy if policy is not None else rejections_module.NullRejectionPolicy()
        )

    def export(self, context: SyncContext) -> ExportResult:
        import platform

        # Deferred: two-way dep with config_sync; call-time keeps it acyclic (SOLID M2).
        import config_sync

        files = {}
        for filename in SNAPSHOT_CONFIG_FILES:
            path = context.claude_dir / filename
            if not path.exists():
                continue
            if filename == "settings.json":
                files[filename] = config_sync.json.dumps(
                    config_sync._clean_settings(config_sync._read(path))
                )
            else:
                files[filename] = config_sync._read(path)
        for directory in SNAPSHOT_CONFIG_DIRS:
            files.update(config_sync._collect_dir(context.claude_dir, directory))

        machine_id = _machine_id(context)
        snapshot = {
            "machine_id": machine_id,
            "hostname": platform.node(),
            "platform": platform.system(),
            "timestamp": datetime.now(UTC).isoformat(),
            "files": files,
        }
        machines_dir = context.repo_dir / "machines"
        machines_dir.mkdir(parents=True, exist_ok=True)
        (machines_dir / f"{machine_id}.json").write_text(
            config_sync.json.dumps(snapshot, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return ExportResult(self.name, written=[f"machines/{machine_id}.json"])

    def apply(self, context: SyncContext) -> ApplyResult:
        # Deferred: two-way dep with config_sync; call-time keeps it acyclic (SOLID M2).
        import config_sync

        result = ApplyResult(self.name)
        consolidated = context.repo_dir / "consolidated" / "snapshot.json"
        if not consolidated.exists():
            return result
        snapshot = config_sync.json.loads(consolidated.read_text(encoding="utf-8"))
        files = snapshot.get("files", {})

        import config_sync_rejections as rejections_module

        # The empty string, NOT `snapshot["timestamp"]` — exactly as
        # `cmd_consolidate` passes "" for `base_files`, and for the same reason.
        # The consolidated snapshot's timestamp is its *generation* time:
        # `cmd_consolidate` stamps `datetime.now(UTC)` on every run, so it is
        # always strictly newer than any recorded rejection and every rejection
        # would read as stale intent — making `--scope local` inert. Content
        # provenance is decided at the consolidate layer, where the contributing
        # machine snapshot's own timestamp is still known; a local veto here is
        # undone with `unreject`, never by the clock. Do not restore the field.
        files, removed_addresses = rejections_module.filter_snapshot_files(
            files, self._policy, ""
        )
        result.rejection_removals.extend(removed_addresses)
        # Which `${...}` in a hook command config-sync itself minted. Absent on
        # an older snapshot, which correctly means none are known to be ours.
        minted_tokens = snapshot.get("root_tokens", ())
        for relative_path, content in files.items():
            if relative_path.startswith(_SKIP_APPLY_PREFIXES):
                result.skipped.append(relative_path)
                continue
            destination = context.claude_dir / relative_path
            if not config_sync._is_within(destination, context.claude_dir):
                result.skipped.append(relative_path)
                continue
            outcome = config_sync._apply_snapshot_file(
                destination, relative_path, content, minted_tokens
            )
            (result.applied if outcome == "applied" else result.skipped).append(
                relative_path
            )
        return result


def apply_propagators(context=None) -> list:
    """Composition root for the local-file apply sweep (Snapshot + ContentBundle).

    Apply writes LOCAL files only, so it is handed the COMPOSITE policy — both
    scopes are correct here, unlike `cmd_consolidate`, which writes shared state
    and gets a network-only policy.
    """
    if context is None:
        return [SnapshotPropagator(), ContentBundlePropagator()]

    import config_sync_rejections as rejections_module

    # `_machine_id(context)` from THIS module, never config_sync's argless one:
    # the context-injected variant honours the caller's claude_dir, so a test
    # cannot be made to read the operator's real ~/.claude.
    policy = rejections_module.CompositeRejectionPolicy(
        [
            rejections_module.LocalRejectionStore(
                context.claude_dir / "config-sync-rejections.json"
            ),
            rejections_module.SharedRejectionStore(
                context.repo_dir, _machine_id(context)
            ),
        ]
    )
    return [SnapshotPropagator(policy=policy), ContentBundlePropagator()]
