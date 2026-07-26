import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import config_sync_propagators as propagators  # noqa: E402


def test_snapshot_and_bundle_satisfy_both_protocols():
    snapshot = propagators.SnapshotPropagator()
    bundle = propagators.ContentBundlePropagator()
    assert isinstance(snapshot, propagators.Exporter)
    assert isinstance(snapshot, propagators.Applier)
    assert isinstance(bundle, propagators.Exporter)
    assert isinstance(bundle, propagators.Applier)


def test_apply_propagators_returns_snapshot_and_bundle():
    names = {propagator.name for propagator in propagators.apply_propagators()}
    assert names == {"snapshot", "content-bundle"}
