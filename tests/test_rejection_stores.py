"""Both stores satisfy one contract; each has one behaviour the other cannot.

The contract suite is parameterised over both constructors, so substituting
either is proven rather than assumed (LSP).
"""

import json

import pytest

from config_sync_rejections import (
    CorruptRejectionLedgerError,
    LocalRejectionStore,
    RejectionRecord,
    SharedRejectionStore,
)


def _record(
    rejection_id="abc123def456", scope="local", rejected_at="2026-08-03T09:00:00+00:00"
):
    return RejectionRecord(
        id=rejection_id,
        kind="snapshot-file",
        address="rules/a.md",
        scope=scope,
        rejected_at=rejected_at,
        machine_id="machine-a",
    )


def _local(tmp_path):
    return LocalRejectionStore(tmp_path / "config-sync-rejections.json")


def _shared(tmp_path):
    return SharedRejectionStore(tmp_path / "repo", "machine-a")


@pytest.fixture(params=[_local, _shared], ids=["local", "shared"])
def store(request, tmp_path):
    return request.param(tmp_path)


def test_absent_backing_file_reads_as_empty(store):
    assert store.all() == []


def test_recorded_rejection_round_trips(store):
    written = _record(scope=store.scope)
    store.record(written)
    assert store.all() == [written]


def test_recording_the_same_id_twice_replaces_rather_than_duplicates(store):
    store.record(_record(scope=store.scope, rejected_at="2026-08-03T09:00:00+00:00"))
    store.record(_record(scope=store.scope, rejected_at="2026-08-03T10:00:00+00:00"))
    assert [found.rejected_at for found in store.all()] == ["2026-08-03T10:00:00+00:00"]


def test_forget_removes_the_record(store):
    store.record(_record(scope=store.scope))
    store.forget("abc123def456")
    assert store.all() == []


def test_forgetting_an_unknown_id_is_a_no_op(store):
    store.record(_record(scope=store.scope))
    store.forget("notarealid00")
    assert len(store.all()) == 1


def test_corrupt_backing_file_fails_closed(store, tmp_path):
    store.record(_record(scope=store.scope))
    for corruptible in tmp_path.rglob("*.json"):
        corruptible.write_text("{not json", encoding="utf-8")
    with pytest.raises(CorruptRejectionLedgerError):
        store.all()


def test_structurally_malformed_backing_file_fails_closed(store, tmp_path):
    store.record(_record(scope=store.scope))
    malformed_payload = json.dumps({"rejections": [{"address": "x"}]})
    for corruptible in tmp_path.rglob("*.json"):
        corruptible.write_text(malformed_payload, encoding="utf-8")
    with pytest.raises(CorruptRejectionLedgerError):
        store.all()


def test_shared_store_reads_every_machines_file(tmp_path):
    SharedRejectionStore(tmp_path / "repo", "machine-a").record(
        _record(rejection_id="aaaaaaaaaaaa", scope="network")
    )
    SharedRejectionStore(tmp_path / "repo", "machine-b").record(
        _record(rejection_id="bbbbbbbbbbbb", scope="network")
    )
    seen = SharedRejectionStore(tmp_path / "repo", "machine-a").all()
    assert {found.id for found in seen} == {"aaaaaaaaaaaa", "bbbbbbbbbbbb"}


def test_shared_store_writes_only_its_own_machine_file(tmp_path):
    SharedRejectionStore(tmp_path / "repo", "machine-a").record(
        _record(scope="network")
    )
    written = sorted(
        path.name for path in (tmp_path / "repo" / "rejections").glob("*.json")
    )
    assert written == ["machine-a.json"]


def test_shared_store_forget_leaves_another_machines_record_alone(tmp_path):
    SharedRejectionStore(tmp_path / "repo", "machine-b").record(
        _record(rejection_id="bbbbbbbbbbbb", scope="network")
    )
    SharedRejectionStore(tmp_path / "repo", "machine-a").forget("bbbbbbbbbbbb")
    assert len(SharedRejectionStore(tmp_path / "repo", "machine-a").all()) == 1


def test_local_store_payload_is_a_plain_list_of_records(tmp_path):
    store = _local(tmp_path)
    store.record(_record())
    payload = json.loads(
        (tmp_path / "config-sync-rejections.json").read_text(encoding="utf-8")
    )
    assert payload["rejections"][0]["address"] == "rules/a.md"
