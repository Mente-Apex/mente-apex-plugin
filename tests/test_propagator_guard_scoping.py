"""The mass-delete guard has to be per-kind, and it has to be recoverable.

Two holes in the first version: the ledger was rewritten with the reduced set
even when the guard refused, so the machine forgot it had ever exported those
bundles and the documented override then did nothing; and the trigger compared
against the WHOLE previous export, so a single kind being wiped -- the very
"directory emptied by a failed move" the guard's own text names -- slipped
through.
"""

import config_sync_propagators as propagators
from config_sync_propagators import ContentBundlePropagator, SyncContext


def _context(tmp_path):
    return SyncContext(claude_dir=tmp_path / "c", repo_dir=tmp_path / "r")


def _machine_id_file(tmp_path):
    (tmp_path / "c").mkdir(parents=True, exist_ok=True)
    (tmp_path / "c" / "config-sync-machine-id").write_text("m1", encoding="utf-8")


def _skill(tmp_path, name):
    skill_dir = tmp_path / "c" / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text("body", encoding="utf-8")


def _agent(tmp_path, name):
    agents = tmp_path / "c" / "agents"
    agents.mkdir(parents=True, exist_ok=True)
    (agents / f"{name}.md").write_text("body", encoding="utf-8")


class TestTheGuardIsRecoverable:
    def test_a_refusal_does_not_erase_the_ledger_it_depends_on(self, tmp_path):
        """The index was rewritten with the reduced `current` even on refusal,
        so the second run had nothing to compare against and the override
        silently tombstoned nothing."""
        _machine_id_file(tmp_path)
        (tmp_path / "c" / "skills").mkdir(parents=True)
        propagator = ContentBundlePropagator()
        context = _context(tmp_path)
        previous = {"skill/alpha", "skill/beta", "skill/gamma"}
        propagator._ledger.record_export(context.repo_dir, "m1", previous)

        propagator.export(context)

        assert (
            propagator._ledger.previously_exported(context.repo_dir, "m1") == previous
        )

    def test_the_override_works_on_the_run_after_a_refusal(self, tmp_path, monkeypatch):
        """The warning tells the operator to re-run with the override. It has
        to actually do something when they do."""
        _machine_id_file(tmp_path)
        (tmp_path / "c" / "skills").mkdir(parents=True)
        propagator = ContentBundlePropagator()
        context = _context(tmp_path)
        propagator._ledger.record_export(
            context.repo_dir, "m1", {"skill/alpha", "skill/beta", "skill/gamma"}
        )

        propagator.export(context)  # refused

        monkeypatch.setattr(
            propagators, "ENVIRON", {propagators.MASS_DELETE_OVERRIDE: "1"}
        )
        result = propagator.export(context)

        assert sorted(result.tombstoned) == [
            "skill/alpha",
            "skill/beta",
            "skill/gamma",
        ]

    def test_an_unscanned_kind_does_not_erase_its_ledger_entries_either(self, tmp_path):
        """Otherwise the unmounted-volume warning fires once and the machine
        then forgets those bundles were ever exported."""
        _machine_id_file(tmp_path)
        propagator = ContentBundlePropagator()
        context = _context(tmp_path)
        previous = {"skill/alpha", "skill/beta"}
        propagator._ledger.record_export(context.repo_dir, "m1", previous)

        propagator.export(context)
        second = propagator.export(context)

        assert len(second.warnings) == 2
        assert (
            propagator._ledger.previously_exported(context.repo_dir, "m1") == previous
        )


class TestTheGuardIsPerKind:
    def test_wiping_every_skill_is_refused_even_when_an_agent_survives(self, tmp_path):
        """`candidates != previously_exported` meant one surviving bundle of
        any kind disarmed the guard entirely -- so five skills emptied by a
        failed move were tombstoned without a word."""
        _machine_id_file(tmp_path)
        (tmp_path / "c" / "skills").mkdir(parents=True)
        _agent(tmp_path, "keeper")
        propagator = ContentBundlePropagator()
        context = _context(tmp_path)
        propagator._ledger.record_export(
            context.repo_dir,
            "m1",
            {"skill/a", "skill/b", "skill/c", "agent/keeper.md"},
        )

        result = propagator.export(context)

        assert not any(entry.startswith("skill/") for entry in result.tombstoned)
        assert any("REFUSED" in warning for warning in result.warnings)

    def test_a_partial_deletion_within_a_kind_is_still_allowed(self, tmp_path):
        """The control: two of three gone is the ordinary case."""
        _machine_id_file(tmp_path)
        _skill(tmp_path, "a")
        propagator = ContentBundlePropagator()
        context = _context(tmp_path)
        propagator._ledger.record_export(
            context.repo_dir, "m1", {"skill/a", "skill/b", "skill/c"}
        )

        result = propagator.export(context)

        assert sorted(result.tombstoned) == ["skill/b", "skill/c"]

    def test_a_kind_with_one_previous_bundle_is_below_the_threshold(self, tmp_path):
        """A single bundle disappearing is as likely deliberate as not, and
        guarding it would be noise."""
        _machine_id_file(tmp_path)
        (tmp_path / "c" / "skills").mkdir(parents=True)
        propagator = ContentBundlePropagator()
        context = _context(tmp_path)
        propagator._ledger.record_export(context.repo_dir, "m1", {"skill/only"})

        result = propagator.export(context)

        assert result.tombstoned == ["skill/only"]


class TestCorruptPluginStateReachesTheOperator:
    def test_the_cli_reports_it_rather_than_a_traceback(self, tmp_path, monkeypatch):
        import config_sync
        import config_sync_plugins

        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir(parents=True)
        (plugins_dir / "installed_plugins.json").write_text("{oops", encoding="utf-8")
        monkeypatch.setattr(config_sync, "CLAUDE_DIR", tmp_path)
        monkeypatch.setattr(
            config_sync,
            "COMMANDS",
            {
                "boom": (
                    lambda: config_sync_plugins._read_installed_plugins(tmp_path),
                    0,
                )
            },
        )
        monkeypatch.setattr(config_sync.sys, "argv", ["config_sync.py", "boom"])

        import pytest

        with pytest.raises(SystemExit) as exit_info:
            config_sync.main()

        assert exit_info.value.code == 2
