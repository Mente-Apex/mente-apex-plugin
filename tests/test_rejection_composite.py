"""Fanning a query across stores, and letting one machine overrule another."""

from config_sync_rejections import (
    CompositeRejectionPolicy,
    LocalRejectionStore,
    NullRejectionPolicy,
    RejectionRecord,
    RejectionTarget,
    SharedRejectionStore,
    rejection_id_of,
)

TARGET = RejectionTarget(kind="snapshot-file", address="rules/a.md")
TARGET_ID = rejection_id_of("snapshot-file", "rules/a.md")
OLD_CONTENT = "2026-08-03T08:00:00+00:00"


def _rejection(
    rejected_at, machine_id="machine-a", scope="network", revives=None, suffix=""
):
    return RejectionRecord(
        id=(TARGET_ID + suffix) if revives else TARGET_ID,
        kind="snapshot-file",
        address="rules/a.md",
        scope=scope,
        rejected_at=rejected_at,
        machine_id=machine_id,
        revives=revives,
    )


def _policy(tmp_path):
    return CompositeRejectionPolicy(
        [
            LocalRejectionStore(tmp_path / "local.json"),
            SharedRejectionStore(tmp_path / "repo", "machine-a"),
        ]
    )


def test_null_policy_never_rejects():
    assert not NullRejectionPolicy().is_rejected(TARGET, OLD_CONTENT)


def test_unrecorded_target_is_not_rejected(tmp_path):
    assert not _policy(tmp_path).is_rejected(TARGET, OLD_CONTENT)


def test_a_rejection_in_either_store_suppresses(tmp_path):
    policy = _policy(tmp_path)
    policy.record(_rejection("2026-08-03T09:00:00+00:00", scope="local"))
    assert policy.is_rejected(TARGET, OLD_CONTENT)


def test_content_newer_than_the_rejection_survives(tmp_path):
    policy = _policy(tmp_path)
    policy.record(_rejection("2026-08-03T09:00:00+00:00", scope="local"))
    assert not policy.is_rejected(TARGET, "2026-08-03T11:00:00+00:00")


def test_a_newer_revival_un_suppresses(tmp_path):
    policy = _policy(tmp_path)
    SharedRejectionStore(tmp_path / "repo", "machine-b").record(
        _rejection("2026-08-03T09:00:00+00:00", machine_id="machine-b")
    )
    policy.record(
        _rejection(
            "2026-08-03T10:00:00+00:00", revives=TARGET_ID, suffix="R", scope="network"
        )
    )
    assert not policy.is_rejected(TARGET, OLD_CONTENT)


def test_a_revival_older_than_the_rejection_does_not_un_suppress(tmp_path):
    policy = _policy(tmp_path)
    SharedRejectionStore(tmp_path / "repo", "machine-b").record(
        _rejection("2026-08-03T10:00:00+00:00", machine_id="machine-b")
    )
    policy.record(
        _rejection(
            "2026-08-03T09:00:00+00:00", revives=TARGET_ID, suffix="R", scope="network"
        )
    )
    assert policy.is_rejected(TARGET, OLD_CONTENT)


def test_record_routes_to_the_store_matching_its_scope(tmp_path):
    policy = _policy(tmp_path)
    policy.record(_rejection("2026-08-03T09:00:00+00:00", scope="network"))
    assert (tmp_path / "repo" / "rejections" / "machine-a.json").exists()
    assert not (tmp_path / "local.json").exists()


def test_forget_reaches_every_store(tmp_path):
    policy = _policy(tmp_path)
    policy.record(_rejection("2026-08-03T09:00:00+00:00", scope="local"))
    policy.forget(TARGET_ID)
    assert not policy.is_rejected(TARGET, OLD_CONTENT)


def test_a_local_scoped_record_in_the_shared_store_is_ignored(tmp_path):
    """Controller ruling: CompositeRejectionPolicy.all() must honour each
    record's own scope against the store it came from, not just union
    everything every injected store hands back.

    A local-scoped record can end up sitting in a shared-repo file (an older
    client, a hand edit, a bad merge). A network-only policy — exactly what
    `cmd_consolidate` is handed in Task 5 — must never let that record count,
    or a private veto would silently strip content from shared state for
    everyone. This writes straight into the shared store, bypassing the
    policy's scope-routing on `record()`, to prove the filter lives in the
    policy's read path too.
    """
    shared_store = SharedRejectionStore(tmp_path / "repo", "machine-a")
    shared_store.record(_rejection("2026-08-03T09:00:00+00:00", scope="local"))
    network_only_policy = CompositeRejectionPolicy([shared_store])
    assert not network_only_policy.is_rejected(TARGET, OLD_CONTENT)
    assert network_only_policy.all() == []
