"""Tests for the empty / entrypoint-less export guard (#73).

`config-sync` export must never write an empty or entrypoint-less skill/agent
bundle. A locally-broken source (a skill dir left with no SKILL.md — e.g. only
`__pycache__` scratch that the export filter drops) previously produced an EMPTY
payload that clobbered the last-good repo bundle and entered the export ledger,
silently propagating a broken skill network-wide. Export must skip-and-warn such
sources and leave any existing bundle intact — without tombstoning it.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import config_sync_propagators as propagators  # noqa: E402


def _write_skill(claude_dir, name, files):
    skill_dir = claude_dir / "skills" / name
    for relative, content in files.items():
        target = skill_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    return skill_dir


def test_export_skips_and_warns_skill_with_only_scratch(tmp_path):
    """A skill dir whose only content is filtered-out scratch yields an empty
    payload: export must NOT write a bundle and must record a warning."""
    claude_dir = tmp_path / "c"
    repo_dir = tmp_path / "r"
    _write_skill(claude_dir, "memory", {"__pycache__/mod.cpython-314.pyc": "bytecode"})
    context = propagators.SyncContext(claude_dir=claude_dir, repo_dir=repo_dir)

    result = propagators.ContentBundlePropagator().export(context)

    bundle = repo_dir / "bundles" / "skills" / "memory"
    assert not bundle.exists()                  # nothing empty written
    assert "skill/memory" not in result.written
    assert any("memory" in warning for warning in result.warnings)
    assert "skill/memory" not in result.tombstoned   # not a deletion


def test_export_skips_skill_missing_entrypoint(tmp_path):
    """A skill dir with authored files but no SKILL.md is broken — export skips it."""
    claude_dir = tmp_path / "c"
    repo_dir = tmp_path / "r"
    _write_skill(claude_dir, "memory", {"references/guide.md": "orphaned content"})
    context = propagators.SyncContext(claude_dir=claude_dir, repo_dir=repo_dir)

    result = propagators.ContentBundlePropagator().export(context)

    bundle = repo_dir / "bundles" / "skills" / "memory"
    assert not bundle.exists()
    assert "skill/memory" not in result.written
    assert any("memory" in warning for warning in result.warnings)


def test_export_does_not_clobber_good_bundle_with_empty_payload(tmp_path):
    """The last-good bundle must survive when the local source goes empty."""
    claude_dir = tmp_path / "c"
    repo_dir = tmp_path / "r"

    # A previously-exported, valid bundle already lives in the repo.
    good_bundle = repo_dir / "bundles" / "skills" / "memory"
    good_bundle.mkdir(parents=True)
    (good_bundle / "SKILL.md").write_text("# memory")
    (good_bundle / propagators.MANIFEST_NAME).write_text(propagators.json.dumps({
        "name": "memory", "kind": "skill", "is_dir": True,
        "content_hash": propagators._content_hash({"SKILL.md": b"# memory"}),
        "exported_at": "2026-01-01T00:00:00+00:00", "machine_id": "m",
    }))

    # The local source is now broken (SKILL.md gone, only scratch remains).
    _write_skill(claude_dir, "memory", {"__pycache__/x.pyc": "bytecode"})
    context = propagators.SyncContext(claude_dir=claude_dir, repo_dir=repo_dir)

    propagators.ContentBundlePropagator().export(context)

    assert (good_bundle / "SKILL.md").read_text() == "# memory"   # untouched
