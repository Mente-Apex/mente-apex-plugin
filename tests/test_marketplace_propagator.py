from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import config_sync_plugins as plugins_module  # noqa: E402
import config_sync_propagators as propagators  # noqa: E402


def _setup(claude_dir, installed, marketplaces, machine_id="m1"):
    plugins_dir = claude_dir / "plugins"
    plugins_dir.mkdir(parents=True)
    (plugins_dir / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": installed}))
    (plugins_dir / "known_marketplaces.json").write_text(json.dumps(marketplaces))
    (claude_dir / "config-sync-machine-id").write_text(machine_id)


def test_export_records_only_resolvable_marketplace_plugins(tmp_path):
    claude_dir = tmp_path / ".claude"
    _setup(
        claude_dir,
        installed={
            "superpowers@claude-plugins-official": [{"version": "6.1.1"}],
            "private-thing@nowhere": [{"version": "0.1"}],       # marketplace not registered → excluded
        },
        marketplaces={"claude-plugins-official": {
            "source": {"source": "github", "repo": "anthropics/claude-plugins-official"}}},
    )
    context = propagators.SyncContext(claude_dir=claude_dir, repo_dir=tmp_path / "repo")

    result = plugins_module.MarketplacePropagator().export(context)

    manifest = json.loads((context.repo_dir / "plugins" / "m1.json").read_text())
    assert list(manifest["plugins"]) == ["superpowers@claude-plugins-official"]   # unresolvable excluded
    assert manifest["plugins"]["superpowers@claude-plugins-official"]["version"] == "6.1.1"
    assert manifest["marketplaces"]["claude-plugins-official"]["source"]["repo"] == \
        "anthropics/claude-plugins-official"
    assert "plugins/m1.json" in result.written


def test_export_is_change_gated(tmp_path):
    claude_dir = tmp_path / ".claude"
    _setup(claude_dir, installed={"superpowers@claude-plugins-official": [{"version": "6.1.1"}]},
           marketplaces={"claude-plugins-official": {"source": {"source": "github", "repo": "a/b"}}})
    context = propagators.SyncContext(claude_dir=claude_dir, repo_dir=tmp_path / "repo")
    marketplace_propagator = plugins_module.MarketplacePropagator()

    marketplace_propagator.export(context)
    second = marketplace_propagator.export(context)
    assert second.written == [] and any("unchanged" in entry for entry in second.skipped)
