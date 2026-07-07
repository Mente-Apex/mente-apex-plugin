import config_sync


def test_propagate_export_writes_snapshot_and_bundles(claude_home, tmp_path, capsys):
    (claude_home / "CLAUDE.md").write_text("hi")
    (claude_home / "skills" / "demo").mkdir(parents=True)
    (claude_home / "skills" / "demo" / "SKILL.md").write_text("# d")
    repo = tmp_path / "repo"
    repo.mkdir()

    config_sync.cmd_propagate_export(str(repo))
    capsys.readouterr()

    assert list((repo / "machines").glob("*.json"))
    assert (repo / "bundles" / "skills" / "demo" / "SKILL.md").read_text() == "# d"


def test_propagate_apply_reports_conflicts(claude_home, tmp_path, capsys):
    # Local divergent skill vs a repo bundle with a different hash → conflict reported.
    (claude_home / "skills" / "demo").mkdir(parents=True)
    (claude_home / "skills" / "demo" / "SKILL.md").write_text("LOCAL")
    bundle = tmp_path / "repo" / "bundles" / "skills" / "demo"
    bundle.mkdir(parents=True)
    (bundle / "SKILL.md").write_text("REPO")
    (bundle / "bundle-manifest.json").write_text(config_sync.json.dumps({
        "name": "demo", "kind": "skill", "is_dir": True,
        "content_hash": "differs", "exported_at": "2026-01-01T00:00:00+00:00", "machine_id": "m",
    }))

    config_sync.cmd_propagate_apply(str(tmp_path / "repo"))
    payload = config_sync.json.loads(capsys.readouterr().out)

    assert payload["content-bundle"]["conflicts"][0]["name"] == "demo"
