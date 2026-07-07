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
