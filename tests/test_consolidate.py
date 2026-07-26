import config_sync


def _snap(machine, timestamp, model):
    return config_sync.json.dumps(
        {
            "machine_id": machine,
            "timestamp": timestamp,
            "files": {"settings.json": config_sync.json.dumps({"model": model})},
        }
    )


def _make_repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "machines").mkdir(parents=True)
    (repo / "consolidated").mkdir(parents=True)
    return repo


def test_consolidate_most_recent_timestamp_wins(tmp_path):
    repo = _make_repo(tmp_path)
    # 'aaa' is alphabetically first but OLDER; 'zzz' is newer and must win.
    (repo / "machines" / "aaa.json").write_text(
        _snap("aaa", "2026-01-01T00:00:00+00:00", "opus")
    )
    (repo / "machines" / "zzz.json").write_text(
        _snap("zzz", "2026-07-01T00:00:00+00:00", "sonnet")
    )

    config_sync.cmd_consolidate(str(repo))

    consolidated = config_sync.json.loads(
        (repo / "consolidated" / "snapshot.json").read_text()
    )
    settings = config_sync.json.loads(consolidated["files"]["settings.json"])
    assert settings["model"] == "sonnet"


def test_consolidate_unions_markdown_bullets(tmp_path, monkeypatch):
    # Force the structured section-union fallback (no nested claude -p) so the
    # merge is deterministic and offline.
    monkeypatch.setattr(config_sync.shutil, "which", lambda name: None)
    repo = _make_repo(tmp_path)
    for machine, timestamp, body in [
        ("aaa", "2026-01-01T00:00:00+00:00", "# Prefs\n- Prefers light mode\n"),
        (
            "bbb",
            "2026-02-01T00:00:00+00:00",
            "# Prefs\n- Prefers dark mode\n- Enable telemetry\n",
        ),
    ]:
        (repo / "machines" / f"{machine}.json").write_text(
            config_sync.json.dumps(
                {
                    "machine_id": machine,
                    "timestamp": timestamp,
                    "files": {"CLAUDE.md": body},
                }
            )
        )

    config_sync.cmd_consolidate(str(repo))

    claude_md = config_sync.json.loads(
        (repo / "consolidated" / "snapshot.json").read_text()
    )["files"]["CLAUDE.md"]
    assert "<<<<<<<" not in claude_md
    assert "- Prefers light mode" in claude_md
    assert "- Prefers dark mode" in claude_md
    assert "- Enable telemetry" in claude_md
