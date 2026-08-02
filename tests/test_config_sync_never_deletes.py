"""Import adds and updates. It must never delete.

That is what `_merge_import_settings`' docstring promised and what a top-level
`merged[key] = value` overlay did the opposite of: any key present on both
sides was replaced wholesale, so a pull carrying only `PreToolUse` erased the
`SessionStart` hooks this machine had, and a snapshot carrying one permission
erased the rest.

Also here: the section merge's two content-destroying parsing bugs, the
fabricated conflicts that dropped a line rather than unioning it, and the
sentinel that got written into a live hook command it could not expand.
"""

import json

import pytest

import config_sync
import config_sync_roots
from config_sync import _deep_merge, _drop_unresolvable_hooks, _merge_import_settings
from config_sync_merge import _line_key, _parse_sections, _section_union


class TestImportNeverDeletesNestedSettings:
    def test_a_hook_event_only_this_machine_has_survives_a_pull(self):
        """The reproduced case: local has PreToolUse and SessionStart, the
        snapshot carries only PreToolUse, and SessionStart was erased."""
        local = {
            "hooks": {
                "PreToolUse": [{"matcher": "Bash", "hooks": [{"command": "a"}]}],
                "SessionStart": [{"matcher": "*", "hooks": [{"command": "b"}]}],
            }
        }
        incoming = {
            "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"command": "a"}]}]}
        }

        merged = _merge_import_settings(incoming, local)

        assert "SessionStart" in merged["hooks"]

    def test_a_permission_only_this_machine_has_survives_a_pull(self):
        local = {"permissions": {"allow": ["Bash(git:*)", "Bash(uv:*)"]}}
        incoming = {"permissions": {"allow": ["Bash(git:*)"]}}

        merged = _merge_import_settings(incoming, local)

        assert merged["permissions"]["allow"] == ["Bash(git:*)", "Bash(uv:*)"]

    def test_an_incoming_permission_is_still_added(self):
        """The control: never-delete must not become never-update."""
        local = {"permissions": {"allow": ["Bash(git:*)"]}}
        incoming = {"permissions": {"allow": ["Bash(npm:*)"]}}

        merged = _merge_import_settings(incoming, local)

        assert merged["permissions"]["allow"] == ["Bash(git:*)", "Bash(npm:*)"]

    def test_an_incoming_scalar_still_wins(self):
        """A scalar contradiction is a real decision, and the network's
        reconciled value is the one to take."""
        assert _deep_merge({"model": "opus"}, {"model": "sonnet"}) == {"model": "opus"}

    def test_a_list_union_does_not_duplicate_an_identical_dict_entry(self):
        entry = {"matcher": "Bash", "hooks": [{"command": "a"}]}

        assert _deep_merge([entry], [entry]) == [entry]

    def test_a_local_only_top_level_key_is_untouched(self):
        """A control, not a regression guard: the old top-level overlay already
        preserved local-only keys at the top level. It is here so a future
        change to `_deep_merge` cannot break the easy case while fixing the
        nested one."""
        merged = _merge_import_settings({"model": "opus"}, {"apiKeyHelper": "x"})

        assert merged["apiKeyHelper"] == "x"


class TestTheSectionMergeDoesNotDestroyContent:
    def test_a_repeated_heading_keeps_both_bodies(self):
        """Keyed on the heading line, a second `## Notes` overwrote the first
        during PARSING -- a whole section body gone before any merge began."""
        version_a = "## Notes\nalpha\n\n## Other\nx\n\n## Notes\nbeta\n"

        merged = _section_union(version_a, "## Notes\ngamma\n")

        assert "alpha" in merged
        assert "beta" in merged
        assert "gamma" in merged

    def test_a_repeated_heading_keeps_the_document_order(self):
        sections = _parse_sections("## A\n1\n\n## B\n2\n\n## A\n3\n")

        assert [heading for _, heading, _ in sections] == [
            "__preamble__",
            "## A",
            "## B",
            "## A",
        ]

    def test_a_comment_inside_a_fenced_block_is_not_a_heading(self):
        """`line.startswith("#")` opened a bogus section mid-code-block, and
        the merge then emitted new lines AFTER the closing fence, silently
        breaking the snippet."""
        text = "# Setup\n\n```bash\n# install deps\nuv sync\n```\n"

        sections = _parse_sections(text)

        assert [heading for _, heading, _ in sections] == ["__preamble__", "# Setup"]

    def test_a_shebang_is_not_a_heading(self):
        sections = _parse_sections("```\n#!/usr/bin/env bash\necho hi\n```\n")

        assert [heading for _, heading, _ in sections] == ["__preamble__"]

    def test_a_hash_without_a_space_is_not_a_heading(self):
        """`#include <stdio.h>` is not an ATX heading; `# Real` is."""
        sections = _parse_sections("#include <stdio.h>\n\n# Real\nbody\n")

        assert [heading for _, heading, _ in sections] == ["__preamble__", "# Real"]

    def test_a_real_heading_is_still_a_heading(self):
        """The control for all four guards above."""
        sections = _parse_sections("# Real\nbody\n")

        assert [heading for _, heading, _ in sections] == ["__preamble__", "# Real"]


class TestConflictsAreNotFabricated:
    def test_two_prose_lines_with_urls_are_not_a_conflict(self):
        """`([^:]+):` made `see https://a.example` a line keyed `https`, so two
        different citations contradicted -- and B's line was REMOVED from the
        merged body, kept only inside the marker block."""
        assert _line_key("see https://a.example") is None

    def test_a_long_prose_sentence_is_not_a_key_line(self):
        line = "When the run finishes and the report is written: check the log"

        assert _line_key(line) is None

    def test_a_real_key_value_line_is_still_a_key(self):
        """The control: without it, the tightened rule could pass by never
        detecting a conflict at all."""
        assert _line_key("Default branch: main") == "Default branch"
        assert _line_key("model: opus") == "model"

    def test_a_genuine_contradiction_still_conflicts(self):
        merged = _section_union("## S\nmodel: opus\n", "## S\nmodel: sonnet\n")

        assert "<<<<<<< Machine A" in merged

    def test_differing_url_lines_both_survive_the_merge(self):
        merged = _section_union(
            "## S\nsee https://a.example\n", "## S\nsee https://b.example\n"
        )

        assert "a.example" in merged
        assert "b.example" in merged
        assert "<<<<<<< Machine A" not in merged


class TestAnUnexpandableSentinelIsNeverWrittenToAHook:
    def test_a_hook_whose_token_this_machine_lacks_is_dropped(self):
        """Writing it installed a hook that ran `python3 /hooks/protect.py`
        (the shell expands an undefined variable to nothing) and failed on
        every matching tool call -- reported as `applied`."""
        registry = config_sync_roots.default_registry("/Users/ai", {})
        settings = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [{"command": "python3 ${MENTE_APEX_MEMORY}/h.py"}],
                    }
                ]
            }
        }

        cleaned, dropped = _drop_unresolvable_hooks(
            settings, registry, ["HOME", "MENTE_APEX_MEMORY"]
        )

        assert cleaned["hooks"] == {}
        assert dropped
        assert "MENTE_APEX_MEMORY" in dropped[0]

    def test_a_hook_this_machine_can_expand_is_kept(self):
        registry = config_sync_roots.default_registry(
            "/Users/ai", {"CONFIG_SYNC_ROOT_MEM": "/Users/ai/mem"}
        )
        settings = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [{"command": "python3 /Users/ai/h.py"}],
                    }
                ]
            }
        }

        cleaned, dropped = _drop_unresolvable_hooks(settings, registry)

        assert dropped == []
        assert cleaned["hooks"]["PreToolUse"]

    def test_one_bad_hook_does_not_drop_its_healthy_sibling(self):
        registry = config_sync_roots.default_registry("/Users/ai", {})
        settings = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [
                            {"command": "python3 ${GONE}/h.py"},
                            {"command": "python3 /Users/ai/ok.py"},
                        ],
                    }
                ]
            }
        }

        cleaned, _ = _drop_unresolvable_hooks(settings, registry, ["HOME", "GONE"])

        commands = [
            hook["command"]
            for group in cleaned["hooks"]["PreToolUse"]
            for hook in group["hooks"]
        ]
        assert commands == ["python3 /Users/ai/ok.py"]

    def test_unresolved_tokens_names_only_what_this_machine_lacks(self):
        registry = config_sync_roots.default_registry(
            "/Users/ai", {"CONFIG_SYNC_ROOT_MEM": "/Users/ai/mem"}
        )

        assert registry.unresolved_tokens(
            "${MEM}/a ${GONE}/b", ["HOME", "MEM", "GONE"]
        ) == ["GONE"]

    def test_a_token_the_exporter_never_minted_is_not_ours_to_judge(self):
        """`${CLAUDE_PROJECT_DIR}` and plain shell variables are somebody
        else's; matching every `${...}` deleted working hooks."""
        registry = config_sync_roots.default_registry("/Users/ai", {})

        assert registry.unresolved_tokens("${CLAUDE_PROJECT_DIR}/x", ["HOME"]) == []


class TestWritesAreAtomic:
    def test_a_write_leaves_no_temp_file_behind(self, tmp_path):
        """A control: `write_text` also left no temp file, so this proves
        nothing about atomicity on its own. The failure case below is the
        guard; this one only stops the temp file leaking on the happy path."""
        target = tmp_path / "settings.json"

        config_sync._write(target, '{"model": "opus"}')

        assert target.read_text(encoding="utf-8") == '{"model": "opus"}'
        assert [path.name for path in tmp_path.iterdir()] == ["settings.json"]

    def test_a_failed_write_does_not_truncate_the_existing_file(
        self, tmp_path, monkeypatch
    ):
        """A plain `write_text` truncates first, so a crash mid-write left the
        operator's settings.json (or the whole network's consolidated
        snapshot) half-written."""
        target = tmp_path / "settings.json"
        target.write_text("original", encoding="utf-8")

        def explode(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(config_sync.os, "replace", explode)

        with pytest.raises(OSError):
            config_sync._write(target, "replacement")

        assert target.read_text(encoding="utf-8") == "original"
        assert [path.name for path in tmp_path.iterdir()] == ["settings.json"]


class TestSymlinkedClaudeSubdirectoriesAreNotRefused:
    def test_a_path_under_a_symlinked_subdirectory_is_within(self, tmp_path):
        """`~/.claude/skills -> ~/repos/my-skills` is an ordinary dotfiles
        layout. Resolving both sides made every path under it 'escape', so
        import silently applied nothing and reported success."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        real_skills = tmp_path / "repos" / "my-skills"
        real_skills.mkdir(parents=True)
        (claude_dir / "skills").symlink_to(real_skills, target_is_directory=True)

        assert config_sync._is_within(claude_dir / "skills" / "foo", claude_dir)

    def test_a_traversal_escape_is_still_refused(self, tmp_path):
        """The control: the resolved check still has to catch `../`."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        assert not config_sync._is_within(claude_dir / ".." / "elsewhere", claude_dir)


class TestConsolidateReportsItsConflicts:
    def test_a_conflict_reaches_the_printed_payload(self, tmp_path, capsys):
        """`merge_log` was accumulated and then dropped from both the snapshot
        and the printed output, so conflict markers were written into a live
        CLAUDE.md with no prompt and no warning anywhere."""
        machines = tmp_path / "machines"
        machines.mkdir()
        for name, value in (("a", "opus"), ("b", "sonnet")):
            (machines / f"{name}.json").write_text(
                json.dumps(
                    {
                        "machine_id": name,
                        "timestamp": f"2026-01-0{1 if name == 'a' else 2}T00:00:00Z",
                        "files": {"CLAUDE.md": f"## S\nmodel: {value}\n"},
                    }
                ),
                encoding="utf-8",
            )

        config_sync.cmd_consolidate(str(tmp_path))

        payload = json.loads(capsys.readouterr().out)
        assert payload["conflicts"]
        assert payload["conflicts"][0]["file"] == "CLAUDE.md"
