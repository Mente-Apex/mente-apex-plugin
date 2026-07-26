"""Tests for the BundleExportFilter seam (#44).

Bundles must carry a skill/agent's authored content, never vendored/build/scratch
artefacts (virtualenvs, bytecode caches, node_modules). The filter is an injected
collaborator so the policy is substitutable and the propagator stays open/closed.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import config_sync  # noqa: E402
import config_sync_propagators as propagators  # noqa: E402


class _ExcludeByName:
    """A fake filter that drops any path containing a given segment — lets a test
    assert the propagator honours the INJECTED policy rather than a hard-coded one."""

    def __init__(self, banned_segment):
        self._banned_segment = banned_segment

    def should_include(self, relative_path):
        return self._banned_segment not in relative_path.split("/")


def _write_skill(claude_dir, name, files):
    skill_dir = claude_dir / "skills" / name
    for relative, content in files.items():
        target = skill_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    return skill_dir


# --- DefaultBundleExportFilter unit behaviour ------------------------------

def test_default_filter_excludes_scratch_keeps_authored_content():
    export_filter = propagators.DefaultBundleExportFilter()
    # authored content travels
    assert export_filter.should_include("SKILL.md")
    assert export_filter.should_include("references/guide.md")
    assert export_filter.should_include("scripts/tool.py")
    # vendored / build / scratch is excluded
    assert not export_filter.should_include("venv/bin/python")
    assert not export_filter.should_include(".venv/lib/site.py")
    assert not export_filter.should_include("__pycache__/mod.cpython-314.pyc")
    assert not export_filter.should_include("scripts/mod.pyc")
    assert not export_filter.should_include("node_modules/left-pad/index.js")
    assert not export_filter.should_include(".git/config")
    assert not export_filter.should_include("fixtures/pkg-1.0.dist-info/RECORD")


# --- Export excludes scratch ------------------------------------------------

def test_export_omits_venv_and_pycache_from_bundle(tmp_path):
    claude_dir = tmp_path / "c"
    repo_dir = tmp_path / "r"
    _write_skill(claude_dir, "tdd", {
        "SKILL.md": "# tdd",
        "references/guide.md": "do the thing",
        "venv/bin/python": "ELF-junk",
        "iteration-1/__pycache__/x.cpython-314.pyc": "bytecode",
    })
    context = propagators.SyncContext(claude_dir=claude_dir, repo_dir=repo_dir)

    result = propagators.ContentBundlePropagator().export(context)

    bundle = repo_dir / "bundles" / "skills" / "tdd"
    assert (bundle / "SKILL.md").exists()
    assert (bundle / "references" / "guide.md").exists()
    assert not (bundle / "venv").exists()                       # venv never travels
    assert not (bundle / "iteration-1" / "__pycache__").exists()  # bytecode never travels
    assert "skill/tdd" in result.written


# --- The injected-filter seam (DIP) ----------------------------------------

def test_export_honours_injected_filter(tmp_path):
    claude_dir = tmp_path / "c"
    repo_dir = tmp_path / "r"
    _write_skill(claude_dir, "demo", {"SKILL.md": "keep", "secret/data.txt": "drop"})
    context = propagators.SyncContext(claude_dir=claude_dir, repo_dir=repo_dir)

    propagator = propagators.ContentBundlePropagator(export_filter=_ExcludeByName("secret"))
    propagator.export(context)

    bundle = repo_dir / "bundles" / "skills" / "demo"
    assert (bundle / "SKILL.md").exists()
    assert not (bundle / "secret").exists()   # the INJECTED policy decided this


# --- Apply must not raise a false conflict from local scratch --------------

def test_apply_skips_when_only_local_scratch_differs(tmp_path):
    """Export hashes filtered content; apply must hash the local destination the
    SAME way, or unfiltered scratch (a venv) would make a matching skill look
    changed and raise a spurious conflict on every sync."""
    claude_dir = tmp_path / "c"
    repo_dir = tmp_path / "r"

    # repo bundle == what export writes: only the authored file, hash over filtered payload
    bundle = repo_dir / "bundles" / "skills" / "tdd"
    bundle.mkdir(parents=True)
    (bundle / "SKILL.md").write_text("# tdd")
    (bundle / propagators.MANIFEST_NAME).write_text(propagators.json.dumps({
        "name": "tdd", "kind": "skill", "is_dir": True,
        "content_hash": propagators._content_hash({"SKILL.md": b"# tdd"}),
        "exported_at": "2026-01-01T00:00:00+00:00", "machine_id": "m",
    }))

    # local destination: identical authored content PLUS local-only scratch
    _write_skill(claude_dir, "tdd", {
        "SKILL.md": "# tdd",
        "venv/bin/python": "machine-specific junk",
        "__pycache__/x.pyc": "bytecode",
    })
    context = propagators.SyncContext(claude_dir=claude_dir, repo_dir=repo_dir)

    result = propagators.ContentBundlePropagator().apply(context)

    assert "skill/tdd" in result.skipped
    assert result.conflicts == []   # scratch alone must NOT look like a change


# --- Status inventory counts authored files only ---------------------------

def test_inventory_file_count_excludes_scratch(tmp_path):
    skills = tmp_path / "skills"
    (skills / "real").mkdir(parents=True)
    (skills / "real" / "SKILL.md").write_text("# real")
    (skills / "tdd-workspace" / "venv" / "bin").mkdir(parents=True)
    (skills / "tdd-workspace" / "venv" / "bin" / "python").write_text("junk")
    (skills / "tdd-workspace" / "__pycache__").mkdir(parents=True)
    (skills / "tdd-workspace" / "__pycache__" / "m.pyc").write_text("bc")

    count = config_sync._inventory_file_count(skills, propagators.DefaultBundleExportFilter())

    assert count == 1   # only real/SKILL.md, not the venv/pyc scratch
