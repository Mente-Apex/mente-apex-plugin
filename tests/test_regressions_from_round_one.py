"""Guards for four defects the FIXES introduced, not the original code.

Two of them left the plugin worse than before it was touched: the directory
prune destroyed the very `.git`/`.venv` its fix existed to protect, and the
token check deleted working hooks in the name of preventing broken ones.

Every test here was confirmed to FAIL against the state of the tree
immediately before this file was written.
"""

import subprocess

import config_sync_propagators as propagators
import config_sync_roots
from config_sync import _drop_unresolvable_hooks
from config_sync_propagators import resolve_bundle
from mutation_gate import exit_code_for, run_gate, unverified_reasons


class TestPruningDoesNotDescendIntoExcludedContent:
    """`root.rglob("*")` was unfiltered, so the prune recursed INTO `.git` and
    `.venv` and rmdir'd every empty directory in them -- `git status` in the
    skill afterwards returned "fatal: not a git repository". The previous
    `rmtree` at least failed honestly.
    """

    @staticmethod
    def _skill_with_a_real_checkout(tmp_path):
        skill_dir = tmp_path / "c" / "skills" / "demo"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("LOCAL", encoding="utf-8")
        subprocess.run(
            ["git", "init", "-q", str(skill_dir)], check=True, capture_output=True
        )
        venv_site = skill_dir / ".venv" / "lib" / "python3.14" / "site-packages"
        venv_site.mkdir(parents=True)
        return skill_dir

    @staticmethod
    def _bundle(tmp_path, payload):
        import json

        bundle = tmp_path / "r" / "bundles" / "skills" / "demo"
        bundle.mkdir(parents=True)
        for name, content in payload.items():
            (bundle / name).write_text(content, encoding="utf-8")
        (bundle / propagators.MANIFEST_NAME).write_text(
            json.dumps({"name": "demo", "kind": "skill", "is_dir": True}),
            encoding="utf-8",
        )
        return bundle

    def _context(self, tmp_path):
        return propagators.SyncContext(
            claude_dir=tmp_path / "c", repo_dir=tmp_path / "r"
        )

    def test_the_local_git_checkout_still_works_afterwards(self, tmp_path):
        skill_dir = self._skill_with_a_real_checkout(tmp_path)
        self._bundle(tmp_path, {"SKILL.md": "REPO"})

        resolve_bundle(self._context(tmp_path), "skill", "demo", "repo")

        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=skill_dir,
            capture_output=True,
            text=True,
        )
        assert status.returncode == 0, status.stderr

    def test_empty_directories_inside_git_are_not_removed(self, tmp_path):
        skill_dir = self._skill_with_a_real_checkout(tmp_path)
        self._bundle(tmp_path, {"SKILL.md": "REPO"})

        resolve_bundle(self._context(tmp_path), "skill", "demo", "repo")

        assert (skill_dir / ".git" / "refs" / "heads").is_dir()
        assert (skill_dir / ".venv" / "lib" / "python3.14" / "site-packages").is_dir()

    def test_a_directory_the_bundle_emptied_is_still_pruned(self, tmp_path):
        """The control: the prune exists for a reason and must keep working."""
        skill_dir = tmp_path / "c" / "skills" / "demo"
        (skill_dir / "docs").mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("LOCAL", encoding="utf-8")
        (skill_dir / "docs" / "old.md").write_text("gone", encoding="utf-8")
        self._bundle(tmp_path, {"SKILL.md": "REPO"})

        resolve_bundle(self._context(tmp_path), "skill", "demo", "repo")

        assert not (skill_dir / "docs").exists()

    def test_an_unrelated_empty_directory_the_user_made_is_left_alone(self, tmp_path):
        """Only directories emptied BY the sweep are pruned. A directory the
        user deliberately created empty is not the sweep's business."""
        skill_dir = tmp_path / "c" / "skills" / "demo"
        (skill_dir / "scratch").mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("LOCAL", encoding="utf-8")
        self._bundle(tmp_path, {"SKILL.md": "REPO"})

        resolve_bundle(self._context(tmp_path), "skill", "demo", "repo")

        assert (skill_dir / "scratch").is_dir()

    def test_a_symlinked_directory_does_not_crash_the_install(self, tmp_path):
        skill_dir = tmp_path / "c" / "skills" / "demo"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("LOCAL", encoding="utf-8")
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        (skill_dir / "linkdir").symlink_to(elsewhere, target_is_directory=True)
        self._bundle(tmp_path, {"SKILL.md": "REPO"})

        resolve_bundle(self._context(tmp_path), "skill", "demo", "repo")

        assert (skill_dir / "SKILL.md").read_text(encoding="utf-8") == "REPO"
        assert elsewhere.is_dir()


class TestOnlyConfigSyncRootTokensAreTreatedAsRootTokens:
    """`unresolved_tokens` matched ANY `${...}`, so import deleted hooks using
    `${CLAUDE_PLUGIN_ROOT}` (this repo's own hooks.json), Claude Code's
    documented `${CLAUDE_PROJECT_DIR}`, and ordinary shell variables. A fix
    against broken hooks was deleting healthy ones.
    """

    @staticmethod
    def _settings(command):
        return {
            "hooks": {
                "PreToolUse": [{"matcher": "Bash", "hooks": [{"command": command}]}]
            }
        }

    def _registry(self):
        return config_sync_roots.default_registry("/Users/ai", {})

    def test_the_plugin_root_placeholder_is_kept(self):
        settings = self._settings("python3 ${CLAUDE_PLUGIN_ROOT}/hooks/guard.py")

        cleaned, dropped = _drop_unresolvable_hooks(settings, self._registry())

        assert dropped == []
        assert cleaned["hooks"]["PreToolUse"]

    def test_the_project_dir_placeholder_is_kept(self):
        settings = self._settings('bash "${CLAUDE_PROJECT_DIR}/hooks/x.sh"')

        cleaned, dropped = _drop_unresolvable_hooks(settings, self._registry())

        assert dropped == []
        assert cleaned["hooks"]["PreToolUse"]

    def test_an_ordinary_shell_variable_is_kept(self):
        settings = self._settings("bash -c 'x=1; echo ${x}'")

        cleaned, dropped = _drop_unresolvable_hooks(settings, self._registry())

        assert dropped == []

    def test_an_undeclared_config_sync_root_is_still_dropped(self):
        """The control: a token that really is a config-sync root, and really
        is undeclared here, must still be refused."""
        registry = config_sync_roots.default_registry(
            "/Users/ai", {"CONFIG_SYNC_ROOT_MEM": "/Users/ai/mem"}
        )
        settings = self._settings("python3 ${MENTE_APEX_MEMORY}/hooks/protect.py")
        # The snapshot records which tokens its exporting machine minted, so
        # this one knows the sentinel is ours rather than a shell variable.
        cleaned, dropped = _drop_unresolvable_hooks(
            settings, registry, ["HOME", "MEM", "MENTE_APEX_MEMORY"]
        )

        assert dropped
        assert cleaned["hooks"] == {}

    def test_a_malformed_hooks_block_does_not_crash_the_import(self):
        for malformed in ({"hooks": {"E": ["juststring"]}}, {"hooks": {"E": {"m": 1}}}):
            cleaned, dropped = _drop_unresolvable_hooks(malformed, self._registry())
            assert isinstance(cleaned, dict)

    def test_settings_without_hooks_do_not_gain_an_empty_hooks_key(self):
        cleaned, _ = _drop_unresolvable_hooks({"model": "opus"}, self._registry())

        assert "hooks" not in cleaned


class TestTheProseMutantCountMatchesTheSurvivorList:
    """`mutants_executed_for` excluded `no_op_mutant` and `declaration_error`
    rows from the count while `unverified_reasons` compared that count against
    a survivor list that INCLUDED them. One no-op broke the equality both ways.
    """

    @staticmethod
    def _prose_backend(survivors, executed):
        class FakeProse:
            stack = "prose"
            tool = "prose"

            def available(self, repo_root):
                return True

            def install_hint(self, repo_root):
                return ""

            def survivors(self, repo_root, paths):
                return survivors

            def mutants_executed(self, repo_root):
                return executed

        return FakeProse()

    @staticmethod
    def _row(status):
        from mutation_gate import Survivor

        return Survivor(
            artifact="doc.md",
            location="doc.md § Guard",
            mutant="delete",
            associated_tests=(),
            backend="prose",
            granularity="section",
            status=status,
        )

    def test_a_run_where_pytest_answered_nothing_is_not_clean(self, tmp_path):
        """Every mutant inconclusive plus one no-op: the equality broke and the
        gate exited 0 -- CLEAN -- over a run that verified nothing."""
        rows = (
            self._row("runtime_error"),
            self._row("runtime_error"),
            self._row("no_op_mutant"),
        )

        result = run_gate(tmp_path, ["doc.md"], [self._prose_backend(rows, 2)])

        assert unverified_reasons(result)
        assert exit_code_for(result) != 0

    def test_a_run_with_real_kills_is_not_condemned(self, tmp_path):
        """The inverse: two mutants genuinely killed, plus a no-op and a
        declaration error, was reported as 'nothing was actually verified'."""
        rows = (self._row("declaration_error"), self._row("no_op_mutant"))

        result = run_gate(tmp_path, ["doc.md"], [self._prose_backend(rows, 2)])

        assert not any(
            "inconclusive" in reason for reason in unverified_reasons(result)
        )


class TestAConformantBackendWithoutAMutantCountIsNotPermanentlyRed:
    """`mutants_executed` is documented as OPTIONAL on the Backend Protocol,
    but `unverified_reasons` treated its absence as a blocking reason -- so
    every protocol-conformant third-party or test-double backend made the gate
    exit 2 forever.
    """

    @staticmethod
    def _minimal_backend():
        class MinimalBackend:
            stack = "python"
            tool = "minimal"

            def available(self, repo_root):
                return True

            def install_hint(self, repo_root):
                return "uv add --dev minimal"

            def survivors(self, repo_root, paths):
                return ()

        return MinimalBackend()

    def test_it_does_not_block_the_clean_verdict(self, tmp_path):
        result = run_gate(tmp_path, ["a.py"], [self._minimal_backend()])

        assert exit_code_for(result) == 0

    def test_a_backend_reporting_zero_is_still_blocked(self, tmp_path):
        """The control: an explicit 0 means the tool ran and mutated nothing,
        which is a real vacuous run and must stay blocked."""

        class ZeroBackend:
            stack = "python"
            tool = "zero"

            def available(self, repo_root):
                return True

            def install_hint(self, repo_root):
                return ""

            def survivors(self, repo_root, paths):
                return ()

            def mutants_executed(self, repo_root):
                return 0

        result = run_gate(tmp_path, ["a.py"], [ZeroBackend()])

        assert exit_code_for(result) == 2


class TestUnverifiedReasonsAreVisibleAlongsideSurvivors:
    def test_the_reasons_are_printed_even_when_a_survivor_exists(self, tmp_path):
        """`render_markdown`'s elif chain printed the reasons only when there
        were no survivors, so a run with both got exit 2 and no explanation --
        contradicting the agent docs that tell the reviewer to read them."""
        from mutation_gate import Survivor
        from mutation_gate_report import render_markdown

        survivor = Survivor(
            artifact="a.py",
            location="a.py:1",
            mutant="x -> y",
            associated_tests=(),
            backend="mutmut",
            granularity="line",
        )

        class PartialBackend:
            stack = "python"
            tool = "mutmut"

            def available(self, repo_root):
                return True

            def install_hint(self, repo_root):
                return ""

            def survivors(self, repo_root, paths):
                return (survivor,)

            def mutants_executed(self, repo_root):
                return 0

        result = run_gate(tmp_path, ["a.py"], [PartialBackend()])
        markdown = render_markdown(result, scope="merge-base")

        assert "Survivors" in markdown
        assert "applied no mutants" in markdown
