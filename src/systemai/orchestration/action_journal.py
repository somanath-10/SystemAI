from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from systemai.contracts.models import ActionIntent, ActionJournalStatus, ActionResult
from systemai.orchestration.event_store import EventStore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_ALLOWED: dict[ActionJournalStatus, set[ActionJournalStatus]] = {
    ActionJournalStatus.PREPARED: {ActionJournalStatus.AUTHORIZED, ActionJournalStatus.REJECTED, ActionJournalStatus.FAILED},
    ActionJournalStatus.AUTHORIZED: {ActionJournalStatus.DISPATCHING, ActionJournalStatus.REJECTED, ActionJournalStatus.FAILED},
    ActionJournalStatus.DISPATCHING: {ActionJournalStatus.DISPATCHED, ActionJournalStatus.COMMIT_STATUS_UNKNOWN, ActionJournalStatus.FAILED},
    ActionJournalStatus.DISPATCHED: {ActionJournalStatus.EFFECT_OBSERVED, ActionJournalStatus.COMMIT_STATUS_UNKNOWN, ActionJournalStatus.FAILED},
    ActionJournalStatus.EFFECT_OBSERVED: {ActionJournalStatus.VERIFIED, ActionJournalStatus.FAILED},
    ActionJournalStatus.COMMIT_STATUS_UNKNOWN: {ActionJournalStatus.EFFECT_OBSERVED, ActionJournalStatus.VERIFIED, ActionJournalStatus.FAILED},
    ActionJournalStatus.VERIFIED: set(),
    ActionJournalStatus.REJECTED: set(),
    ActionJournalStatus.FAILED: set(),
}


class ActionJournal:
    def __init__(self, store: EventStore) -> None:
        self.store = store

    def prepare(self, action: ActionIntent) -> None:
        with self.store.connect() as c:
            c.execute(
                """
                INSERT OR REPLACE INTO action_journal(action_id,task_id,node_id,status,intent_json,result_json,token_nonce,idempotency_key,updated_at)
                VALUES(?,?,?,?,?,NULL,NULL,?,?)
                """,
                (
                    action.action_id,
                    action.task_id,
                    action.node_id,
                    ActionJournalStatus.PREPARED.value,
                    json.dumps(action.model_dump(mode="json"), sort_keys=True),
                    action.idempotency_key,
                    _now(),
                ),
            )
        self.store.append("ActionPrepared", {"capability": action.capability}, task_id=action.task_id, node_id=action.node_id, action_id=action.action_id)

    def transition(self, action: ActionIntent, new_status: ActionJournalStatus, *, result: ActionResult | None = None, token_nonce: str | None = None, detail: dict[str, Any] | None = None) -> None:
        with self.store.connect() as c:
            row = c.execute("SELECT status FROM action_journal WHERE action_id=?", (action.action_id,)).fetchone()
            if not row:
                raise KeyError(f"action not prepared: {action.action_id}")
            old = ActionJournalStatus(row["status"])
            if new_status not in _ALLOWED[old]:
                raise RuntimeError(f"invalid action-journal transition: {old.value} -> {new_status.value}")
            c.execute(
                "UPDATE action_journal SET status=?,result_json=COALESCE(?,result_json),token_nonce=COALESCE(?,token_nonce),updated_at=? WHERE action_id=?",
                (
                    new_status.value,
                    json.dumps(result.model_dump(mode="json"), sort_keys=True) if result else None,
                    token_nonce,
                    _now(),
                    action.action_id,
                ),
            )
        self.store.append(
            f"Action{''.join(p.title() for p in new_status.value.split('_'))}",
            detail or {},
            task_id=action.task_id,
            node_id=action.node_id,
            action_id=action.action_id,
        )

    def get(self, action_id: str) -> dict[str, Any] | None:
        with self.store.connect() as c:
            row = c.execute("SELECT * FROM action_journal WHERE action_id=?", (action_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["intent"] = json.loads(d.pop("intent_json"))
        if d.get("result_json"):
            d["result"] = json.loads(d.pop("result_json"))
        return d

    def unresolved(self) -> list[dict[str, Any]]:
        with self.store.connect() as c:
            rows = c.execute(
                "SELECT * FROM action_journal WHERE status IN (?,?,?)",
                (
                    ActionJournalStatus.DISPATCHING.value,
                    ActionJournalStatus.DISPATCHED.value,
                    ActionJournalStatus.COMMIT_STATUS_UNKNOWN.value,
                ),
            ).fetchall()
        return [dict(r) for r in rows]
