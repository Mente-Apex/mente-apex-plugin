from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import config_sync_propagators as propagators  # noqa: E402


class _FakePropagator:
    name = "fake"

    def __init__(self, written):
        self._written = written

    def export(self, context):
        return propagators.ExportResult(self.name, list(self._written), [])

    def apply(self, context):
        return propagators.ApplyResult(self.name, list(self._written), [], [])


def test_run_export_aggregates_injected_propagators(tmp_path):
    context = propagators.SyncContext(claude_dir=tmp_path / "c", repo_dir=tmp_path / "r")
    results = propagators.run_export(context, [_FakePropagator(["a"]), _FakePropagator(["b"])])
    assert [result.propagator for result in results] == ["fake", "fake"]
    assert [entry for result in results for entry in result.written] == ["a", "b"]


def _write_skill(claude_dir, name, files):
    skill_dir = claude_dir / "skills" / name
    for relative, content in files.items():
        target = skill_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    return skill_dir


def test_export_writes_all_files_of_multifile_skill(tmp_path):
    claude_dir = tmp_path / "c"
    repo_dir = tmp_path / "r"
    _write_skill(claude_dir, "demo", {"SKILL.md": "# demo", "scripts/x.py": "print(1)", "fonts.css": "body{}"})
    context = propagators.SyncContext(claude_dir=claude_dir, repo_dir=repo_dir)

    result = propagators.ContentBundlePropagator().export(context)

    bundle = repo_dir / "bundles" / "skills" / "demo"
    assert (bundle / "scripts" / "x.py").read_text() == "print(1)"   # non-.md asset travels (PS2)
    assert (bundle / "fonts.css").read_text() == "body{}"
    assert (bundle / propagators.MANIFEST_NAME).exists()
    assert "skill/demo" in result.written


def test_export_skips_unchanged_and_reexports_changed(tmp_path):
    claude_dir = tmp_path / "c"
    repo_dir = tmp_path / "r"
    _write_skill(claude_dir, "demo", {"SKILL.md": "v1"})
    context = propagators.SyncContext(claude_dir=claude_dir, repo_dir=repo_dir)
    bundle_propagator = propagators.ContentBundlePropagator()

    bundle_propagator.export(context)
    second = bundle_propagator.export(context)
    assert "skill/demo" in second.skipped and "skill/demo" not in second.written   # hash gate (D8)

    (claude_dir / "skills" / "demo" / "SKILL.md").write_text("v2")   # rebuild
    third = bundle_propagator.export(context)
    assert "skill/demo" in third.written                             # re-exports (PS3)
