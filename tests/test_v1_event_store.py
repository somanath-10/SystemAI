from pathlib import Path
from datetime import datetime, timedelta, timezone

import pytest

from systemai.contracts.models import ActionIntent, ActionJournalStatus
from systemai.orchestration import ActionJournal, EventStore, ResourceBusy, ResourceLeaseManager


def test_event_chain_and_action_journal(tmp_path: Path):
    store = EventStore(tmp_path / "events.sqlite3")
    store.append("GoalCreated", {"x": 1}, task_id="t1")
    store.append("PlanCreated", {"x": 2}, task_id="t1")
    assert store.verify_chain()
    action = ActionIntent(task_id="t1", node_id="n1", capability="process.list", expected_result="list")
    journal = ActionJournal(store)
    journal.prepare(action)
    journal.transition(action, ActionJournalStatus.AUTHORIZED)
    journal.transition(action, ActionJournalStatus.DISPATCHING)
    journal.transition(action, ActionJournalStatus.COMMIT_STATUS_UNKNOWN)
    assert journal.get(action.action_id)["status"] == "commit_status_unknown"
    assert len(store.list_events(limit=-1)) == 1


def test_resource_leases_have_fencing_and_conflict(tmp_path: Path):
    store = EventStore(tmp_path / "events.sqlite3")
    mgr = ResourceLeaseManager(store)
    a = mgr.acquire_many(["port:9999", "filesystem:/tmp/a"], task_id="t1", node_id="n1")
    assert len(a) == 2
    assert a[1].fencing_token != a[0].fencing_token
    with pytest.raises(ResourceBusy):
        mgr.acquire_many(["port:9999"], task_id="t2", node_id="n2")
    mgr.release_many(a)
    b = mgr.acquire_many(["port:9999"], task_id="t2", node_id="n2")
    assert b[0].fencing_token > max(x.fencing_token for x in a)


def test_expired_lease_cannot_be_renewed(tmp_path: Path):
    store = EventStore(tmp_path / "events.sqlite3")
    mgr = ResourceLeaseManager(store)
    lease = mgr.acquire_many(["port:9999"], task_id="t1", node_id="n1")[0]
    expired = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    with store.connect() as c:
        c.execute("UPDATE resource_leases SET expires_at=? WHERE lease_id=?", (expired, lease.lease_id))
    with pytest.raises(KeyError):
        mgr.renew(lease.lease_id)
    assert mgr.list_active() == []
