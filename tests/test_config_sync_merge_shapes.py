"""What the deep merge and the atomic write must not do to a real config.

The never-delete union was right about lists of scalars and wrong about lists
of hook matcher GROUPS: a group that gained one hook was appended beside the
old one, so the shared hook fired twice on every matching call. And the atomic
write replaced a symlinked destination with a regular file, quietly detaching
the dotfiles link it was written through.
"""

import json
import stat

import pytest

import config_sync
from config_sync import _deep_merge, _merge_import_settings


def _group(matcher, *commands):
    return {
        "matcher": matcher,
        "hooks": [{"type": "command", "command": command} for command in commands],
    }


class TestHookGroupsMergeByMatcherNotByIdentity:
    def test_a_group_that_gained_a_hook_does_not_become_a_second_group(self):
        """Fingerprinting whole groups meant `{Bash: [protect]}` and
        `{Bash: [protect, audit]}` were two different entries, so both were
        kept and `protect` ran twice on every Bash call."""
        local = {"hooks": {"PreToolUse": [_group("Bash", "protect.py")]}}
        incoming = {"hooks": {"PreToolUse": [_group("Bash", "protect.py", "audit.py")]}}

        merged = _merge_import_settings(incoming, local)
        groups = merged["hooks"]["PreToolUse"]

        assert len(groups) == 1
        commands = [hook["command"] for hook in groups[0]["hooks"]]
        assert commands == ["protect.py", "audit.py"]

    def test_a_shared_hook_is_not_duplicated_across_repeated_pulls(self):
        local = {"hooks": {"PreToolUse": [_group("Bash", "protect.py")]}}
        incoming = {"hooks": {"PreToolUse": [_group("Bash", "protect.py", "audit.py")]}}

        merged = local
        for _ in range(3):
            merged = _merge_import_settings(incoming, merged)

        groups = merged["hooks"]["PreToolUse"]
        assert len(groups) == 1
        assert len(groups[0]["hooks"]) == 2

    def test_a_different_matcher_is_still_a_different_group(self):
        """The control: distinct matchers are genuinely distinct groups."""
        local = {"hooks": {"PreToolUse": [_group("Bash", "a.py")]}}
        incoming = {"hooks": {"PreToolUse": [_group("Edit", "b.py")]}}

        merged = _merge_import_settings(incoming, local)

        assert len(merged["hooks"]["PreToolUse"]) == 2

    def test_a_hook_only_this_machine_has_survives_the_group_merge(self):
        """Never-delete still holds inside a merged group."""
        local = {"hooks": {"PreToolUse": [_group("Bash", "local-only.py")]}}
        incoming = {"hooks": {"PreToolUse": [_group("Bash", "network.py")]}}

        merged = _merge_import_settings(incoming, local)
        commands = [
            hook["command"] for hook in merged["hooks"]["PreToolUse"][0]["hooks"]
        ]

        assert sorted(commands) == ["local-only.py", "network.py"]

    def test_an_ordinary_scalar_list_still_unions_by_value(self):
        """The control: the group-aware path must not disturb plain lists."""
        assert _deep_merge(["b"], ["a"]) == ["a", "b"]

    def test_a_list_of_dicts_without_a_matcher_still_unions_by_fingerprint(self):
        assert _deep_merge([{"x": 1}], [{"x": 1}]) == [{"x": 1}]

    def test_an_unserialisable_entry_does_not_abort_the_import(self):
        """`json.dumps` as the fingerprint raises on anything exotic, which
        would take the whole settings merge down with it."""
        merged = _deep_merge([{1, 2}], ["a"])

        assert "a" in merged


class TestTheAtomicWriteRespectsWhatIsAlreadyThere:
    def test_it_writes_through_a_symlink_rather_than_replacing_it(self, tmp_path):
        """`os.replace` onto the link path detaches it. A dotfiles layout
        symlinks `~/.claude/CLAUDE.md` into a repo, and the old `write_text`
        wrote through -- this is the layout the `_is_within` fix exists to
        support, so breaking it here contradicts that."""
        real = tmp_path / "dotfiles" / "CLAUDE.md"
        real.parent.mkdir()
        real.write_text("original", encoding="utf-8")
        link = tmp_path / "CLAUDE.md"
        link.symlink_to(real)

        config_sync._write(link, "new content")

        assert link.is_symlink()
        assert real.read_text(encoding="utf-8") == "new content"

    def test_it_preserves_the_existing_file_mode(self, tmp_path):
        """settings.json at 0600 came back 0644 -- a config file holding hook
        commands should not silently become world-readable."""
        target = tmp_path / "settings.json"
        target.write_text("{}", encoding="utf-8")
        target.chmod(0o600)

        config_sync._write(target, '{"model": "opus"}')

        assert stat.S_IMODE(target.stat().st_mode) == 0o600

    def test_a_new_file_is_still_written(self, tmp_path):
        """The control."""
        target = tmp_path / "fresh.json"

        config_sync._write(target, "{}")

        assert target.read_text(encoding="utf-8") == "{}"

    def test_the_write_is_still_atomic_for_an_ordinary_file(
        self, tmp_path, monkeypatch
    ):
        target = tmp_path / "settings.json"
        target.write_text("original", encoding="utf-8")

        def explode(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(config_sync.os, "replace", explode)

        with pytest.raises(OSError):
            config_sync._write(target, "replacement")

        assert target.read_text(encoding="utf-8") == "original"
        assert sorted(path.name for path in tmp_path.iterdir()) == ["settings.json"]


class TestConsolidateDoesNotAccumulate:
    def _machine(self, machines_dir, name, day, body):
        (machines_dir / f"{name}.json").write_text(
            json.dumps(
                {
                    "machine_id": name,
                    "timestamp": f"2026-01-{day}T00:00:00Z",
                    "files": {"CLAUDE.md": body},
                }
            ),
            encoding="utf-8",
        )

    def test_repeated_folds_do_not_grow_the_merged_body(self, tmp_path, capsys):
        """Two blank lines were added per fold, unbounded."""
        machines = tmp_path / "machines"
        machines.mkdir()
        self._machine(machines, "a", "01", "## S\n- alpha\n")
        self._machine(machines, "b", "02", "## S\n- beta\n")

        sizes = []
        for _ in range(4):
            config_sync.cmd_consolidate(str(tmp_path))
            capsys.readouterr()
            snapshot = json.loads(
                (tmp_path / "consolidated" / "snapshot.json").read_text(
                    encoding="utf-8"
                )
            )
            sizes.append(len(snapshot["files"]["CLAUDE.md"]))

        assert len(set(sizes[1:])) == 1, f"body kept growing: {sizes}"

    def test_a_resolved_conflict_stops_being_reported(self, tmp_path, capsys):
        """The conflict flag was derived from markers in the merged output, so
        once markers existed they persisted through every later fold and the
        conflict was reported forever."""
        machines = tmp_path / "machines"
        machines.mkdir()
        self._machine(machines, "a", "01", "## S\nmodel: opus\n")
        self._machine(machines, "b", "02", "## S\nmodel: sonnet\n")
        config_sync.cmd_consolidate(str(tmp_path))
        assert json.loads(capsys.readouterr().out)["conflicts"]

        # Both machines now agree: the operator resolved it and pushed.
        self._machine(machines, "a", "03", "## S\nmodel: opus\n")
        self._machine(machines, "b", "04", "## S\nmodel: opus\n")
        config_sync.cmd_consolidate(str(tmp_path))

        assert json.loads(capsys.readouterr().out)["conflicts"] == []


class TestTheSymlinkAllowanceIsBounded:
    """Widening `_is_within` to accept a symlinked `~/.claude/skills` must not
    become "any lexical path is fine": an unbounded prefix check let a snapshot
    write to anywhere on disk through such a link.
    """

    def test_a_path_under_an_operator_created_symlink_is_accepted(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        real = tmp_path / "repos" / "my-skills"
        real.mkdir(parents=True)
        (claude_dir / "skills").symlink_to(real, target_is_directory=True)

        assert config_sync._is_within(claude_dir / "skills" / "foo", claude_dir)

    def test_a_traversal_escape_is_refused(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        assert not config_sync._is_within(claude_dir / ".." / "elsewhere", claude_dir)

    def test_a_nested_traversal_escape_is_refused(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        assert not config_sync._is_within(
            claude_dir / "a" / ".." / ".." / "evil.md", claude_dir
        )

    def test_an_ordinary_path_inside_the_root_is_accepted(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        assert config_sync._is_within(claude_dir / "settings.json", claude_dir)

    def test_safe_dest_still_refuses_the_classic_escapes(self, tmp_path, monkeypatch):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        monkeypatch.setattr(config_sync, "CLAUDE_DIR", claude_dir)

        for escape in ("../evil.md", "/etc/passwd", "a/../../evil.md"):
            assert config_sync._safe_dest(escape) is None


class TestExportRefusesToPublishACorruptSettingsFileAsEmpty:
    def test_clean_settings_raises_rather_than_returning_empty(self):
        import config_sync_hooks

        with pytest.raises(config_sync_hooks.CorruptSettingsError):
            config_sync._clean_settings('{"model": "opus",}')

    def test_a_valid_file_is_still_scrubbed_and_returned(self):
        cleaned = config_sync._clean_settings('{"model": "opus", "env": {"K": "v"}}')

        assert cleaned == {"model": "opus"}
