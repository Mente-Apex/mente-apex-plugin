"""Deletion must be evidence-based, and installing must not destroy.

A bundle's absence from a scan is only a deletion if the scan could have seen
it. `_sources` yields nothing for a directory that does not exist, which read
identically to "the user deleted everything in it" -- so an unmounted volume
tombstoned and rmtree'd the whole set and offered the same deletion to every
other machine.

And `_install` rebuilt a destination from a payload that, by the export
filter's design, never contains `.git` or `.venv` -- so resolving a conflict in
the repo's favour deleted the local skill's own checkout and virtualenv.
"""

import json

import pytest

import config_sync_propagators as propagators
from config_sync_propagators import ContentBundlePropagator, SyncContext


def _context(tmp_path):
    return SyncContext(claude_dir=tmp_path / "c", repo_dir=tmp_path / "r")


def _local_skill(tmp_path, name, body="SKILL"):
    skill_dir = tmp_path / "c" / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")
    return skill_dir


def _machine_id_file(tmp_path, machine_id="m1"):
    (tmp_path / "c").mkdir(parents=True, exist_ok=True)
    (tmp_path / "c" / "config-sync-machine-id").write_text(machine_id, encoding="utf-8")


class TestAVanishedSourceDirectoryIsNotADeletion:
    def test_a_missing_skills_directory_tombstones_nothing(self, tmp_path):
        """The reproduced Critical: `~/.claude/skills` symlinked to an
        unmounted volume tombstoned and rmtree'd every skill bundle, then
        proposed the deletion network-wide."""
        _machine_id_file(tmp_path)
        propagator = ContentBundlePropagator()
        context = _context(tmp_path)
        # Three skills were exported previously; the directory is now gone.
        propagator._ledger.record_export(
            context.repo_dir,
            "m1",
            {"skill/alpha", "skill/beta", "skill/gamma"},
        )

        result = propagator.export(context)

        assert result.tombstoned == []
        assert len(result.warnings) == 3
        assert all("does not exist on this machine" in w for w in result.warnings)

    def test_an_ordinary_single_deletion_still_tombstones(self, tmp_path):
        """The control: the directory exists and one skill really is gone."""
        _machine_id_file(tmp_path)
        _local_skill(tmp_path, "alpha")
        _local_skill(tmp_path, "beta")
        propagator = ContentBundlePropagator()
        context = _context(tmp_path)
        propagator._ledger.record_export(
            context.repo_dir, "m1", {"skill/alpha", "skill/beta", "skill/gamma"}
        )

        result = propagator.export(context)

        assert result.tombstoned == ["skill/gamma"]


class TestDeletingTheEntirePreviousExportStops:
    def test_it_refuses_and_says_so(self, tmp_path):
        _machine_id_file(tmp_path)
        (tmp_path / "c" / "skills").mkdir(parents=True)  # exists, but empty
        propagator = ContentBundlePropagator()
        context = _context(tmp_path)
        propagator._ledger.record_export(
            context.repo_dir, "m1", {"skill/alpha", "skill/beta", "skill/gamma"}
        )

        result = propagator.export(context)

        assert result.tombstoned == []
        assert any("REFUSED to tombstone all 3" in w for w in result.warnings)

    def test_the_override_lets_a_deliberate_clear_out_through(
        self, tmp_path, monkeypatch
    ):
        _machine_id_file(tmp_path)
        (tmp_path / "c" / "skills").mkdir(parents=True)
        monkeypatch.setattr(
            propagators, "ENVIRON", {propagators.MASS_DELETE_OVERRIDE: "1"}
        )
        propagator = ContentBundlePropagator()
        context = _context(tmp_path)
        propagator._ledger.record_export(
            context.repo_dir, "m1", {"skill/alpha", "skill/beta", "skill/gamma"}
        )

        result = propagator.export(context)

        assert sorted(result.tombstoned) == [
            "skill/alpha",
            "skill/beta",
            "skill/gamma",
        ]

    def test_a_partial_deletion_is_untouched_by_the_guard(self, tmp_path):
        """Two of three gone is the ordinary case and must not be refused."""
        _machine_id_file(tmp_path)
        _local_skill(tmp_path, "alpha")
        propagator = ContentBundlePropagator()
        context = _context(tmp_path)
        propagator._ledger.record_export(
            context.repo_dir, "m1", {"skill/alpha", "skill/beta", "skill/gamma"}
        )

        result = propagator.export(context)

        assert sorted(result.tombstoned) == ["skill/beta", "skill/gamma"]


class TestATombstoneSurvivesAnUnexportablePayload:
    def test_a_broken_local_copy_does_not_clear_another_machines_deletion(
        self, tmp_path
    ):
        """Clearing the tombstone before the exportability gate silently
        reverted a deliberate deletion: the tombstone went, no bundle replaced
        it, and a third machine that had not yet applied saw neither -- so it
        re-published the skill and the deletion was undone with nobody
        consenting."""
        _machine_id_file(tmp_path)
        # Local copy exists but is broken: no SKILL.md entrypoint.
        broken = tmp_path / "c" / "skills" / "foo"
        broken.mkdir(parents=True)
        (broken / "notes.md").write_text("leftovers", encoding="utf-8")

        propagator = ContentBundlePropagator()
        context = _context(tmp_path)
        propagator._ledger.tombstone(
            context.repo_dir, "skill", "foo", "other-machine", "2020-01-01T00:00:00Z"
        )

        result = propagator.export(context)

        assert propagator._ledger.tombstone_for(context.repo_dir, "skill", "foo")
        assert any("skipped" in warning for warning in result.warnings)

    def test_a_healthy_re_add_still_clears_the_tombstone(self, tmp_path):
        """The control: a deliberate re-add must still supersede an older
        tombstone, or a deleted skill could never come back."""
        _machine_id_file(tmp_path)
        _local_skill(tmp_path, "foo")
        propagator = ContentBundlePropagator()
        context = _context(tmp_path)
        propagator._ledger.tombstone(
            context.repo_dir, "skill", "foo", "other-machine", "2020-01-01T00:00:00Z"
        )

        propagator.export(context)

        assert (
            propagator._ledger.tombstone_for(context.repo_dir, "skill", "foo") is None
        )


class TestInstallingDoesNotDestroyExcludedContent:
    def test_a_local_git_checkout_and_venv_survive_a_repo_wins_resolution(
        self, tmp_path
    ):
        """`rmtree(destination)` deleted everything and repopulated from a
        payload that never carries `.git` or `.venv`. The filter's contract is
        'this content does not travel', not 'this may be deleted'."""
        skill_dir = _local_skill(tmp_path, "demo", body="LOCAL")
        (skill_dir / ".git").mkdir()
        (skill_dir / ".git" / "HEAD").write_text(
            "ref: refs/heads/main", encoding="utf-8"
        )
        (skill_dir / ".venv").mkdir()
        (skill_dir / ".venv" / "pyvenv.cfg").write_text("home = /x", encoding="utf-8")

        bundle = tmp_path / "r" / "bundles" / "skills" / "demo"
        bundle.mkdir(parents=True)
        (bundle / "SKILL.md").write_text("REPO", encoding="utf-8")
        (bundle / "bundle.json").write_text(
            json.dumps({"name": "demo", "kind": "skill", "is_dir": True}),
            encoding="utf-8",
        )

        propagators.resolve_bundle(_context(tmp_path), "skill", "demo", "repo")

        assert (skill_dir / "SKILL.md").read_text(encoding="utf-8") == "REPO"
        assert (skill_dir / ".git" / "HEAD").exists()
        assert (skill_dir / ".venv" / "pyvenv.cfg").exists()

    def test_a_file_the_bundle_dropped_is_still_removed(self, tmp_path):
        """The control: not destroying must not become not updating. A file
        the bundle no longer carries has to go."""
        skill_dir = _local_skill(tmp_path, "demo", body="LOCAL")
        (skill_dir / "stale.md").write_text("gone soon", encoding="utf-8")

        bundle = tmp_path / "r" / "bundles" / "skills" / "demo"
        bundle.mkdir(parents=True)
        (bundle / "SKILL.md").write_text("REPO", encoding="utf-8")
        (bundle / "bundle.json").write_text(
            json.dumps({"name": "demo", "kind": "skill", "is_dir": True}),
            encoding="utf-8",
        )

        propagators.resolve_bundle(_context(tmp_path), "skill", "demo", "repo")

        assert not (skill_dir / "stale.md").exists()


class TestCorruptPluginStateIsNeverAnEmptyDesiredState:
    def test_reading_it_refuses_rather_than_exporting_no_plugins(self, tmp_path):
        """Mapping the parse error to `{}` published a manifest saying this
        machine desires no plugins, overwriting the good one -- so a plugin
        only this machine had left the network's desired state for good."""
        import config_sync_plugins

        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir(parents=True)
        (plugins_dir / "installed_plugins.json").write_text("{oops", encoding="utf-8")

        with pytest.raises(config_sync_plugins.CorruptPluginStateError):
            config_sync_plugins._read_installed_plugins(tmp_path)

    def test_an_absent_file_is_still_an_empty_dict(self, tmp_path):
        import config_sync_plugins

        assert config_sync_plugins._read_installed_plugins(tmp_path) == {}


class TestAConvergedPluginIsNotUpdatedAgain:
    def test_a_matching_version_is_skipped(self, tmp_path):
        """`current_version` was read into the detail dict and never compared,
        so a converged machine shelled out `claude plugin update` (180s
        timeout each) for every plugin on every run."""
        import config_sync_plugins

        class Reader:
            def known_marketplaces(self):
                return {"official": {}}

            def installed_plugins(self):
                return {"tool@official": {"version": "1.0"}}

        manifest_dir = tmp_path / "r" / "plugins"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "m1.json").write_text(
            json.dumps(
                {
                    "machine_id": "m1",
                    "exported_at": "2026-01-01T00:00:00+00:00",
                    "marketplaces": {"official": {"source": "github"}},
                    "plugins": {"tool@official": {"version": "1.0"}},
                }
            ),
            encoding="utf-8",
        )

        plan = config_sync_plugins.plan_convergence(_context(tmp_path), Reader())

        assert not any(action.verb == "update_plugin" for action in plan.actions)
        assert any("already at 1.0" in entry for entry in plan.skipped)
