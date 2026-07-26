import config_sync


def test_import_rejects_traversal_and_absolute_keys(claude_home, tmp_path):
    outside = (
        claude_home.parent.parent / "ESCAPED.txt"
    )  # tmp_path/ESCAPED.txt (outside ~/.claude)
    abs_escape = tmp_path / "abs-escape.txt"  # absolute key, isolated to this test
    snapshot = tmp_path / "snap.json"
    snapshot.write_text(
        config_sync.json.dumps(
            {
                "files": {
                    "../../ESCAPED.txt": "pwned",
                    str(abs_escape): "pwned",
                    "rules/ok.md": "legit",
                }
            }
        )
    )

    config_sync.cmd_import(str(snapshot))

    assert not outside.exists()
    assert not abs_escape.exists()
    assert (claude_home / "rules" / "ok.md").read_text() == "legit"


def test_safe_dest_accepts_in_tree_rejects_escapes(claude_home):
    assert config_sync._safe_dest("rules/x.md") is not None
    assert config_sync._safe_dest("a/../b.md") is not None  # normalizes in-tree
    assert config_sync._safe_dest("../x") is None
    assert config_sync._safe_dest("../../etc/x") is None
    assert config_sync._safe_dest("/etc/passwd") is None
