from pathlib import Path

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
