from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ApprovalStore:
    """Canonical approval records. UI should render from typed action/kernel data."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init(self) -> None:
        with self._connect() as c:
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS approvals(
                    approval_id TEXT PRIMARY KEY,
                    action_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    approved INTEGER,
                    approved_by TEXT,
                    reason TEXT,
                    canonical_summary TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    decided_at TEXT
                )
                """
            )

    def request(self, *, action_id: str, task_id: str, requested_by: str, canonical_summary: str, reason: str) -> str:
        approval_id = f"approval_{uuid4().hex[:16]}"
        with self._connect() as c:
            c.execute(
                "INSERT INTO approvals VALUES (?,?,?,?,NULL,NULL,?,?,?,NULL)",
                (approval_id, action_id, task_id, requested_by, reason, canonical_summary, _now()),
            )
        return approval_id

    def decide(self, approval_id: str, *, approved: bool, approved_by: str, reason: str | None = None) -> None:
        with self._connect() as c:
            row = c.execute("SELECT approval_id FROM approvals WHERE approval_id=?", (approval_id,)).fetchone()
            if not row:
                raise KeyError(approval_id)
            c.execute(
                "UPDATE approvals SET approved=?, approved_by=?, reason=COALESCE(?, reason), decided_at=? WHERE approval_id=?",
                (1 if approved else 0, approved_by, reason, _now(), approval_id),
            )

    def is_approved(self, approval_id: str, *, action_id: str) -> bool:
        with self._connect() as c:
            row = c.execute(
                "SELECT approved, action_id FROM approvals WHERE approval_id=?", (approval_id,)
            ).fetchone()
        return bool(row and row["action_id"] == action_id and row["approved"] == 1)

    def get(self, approval_id: str) -> dict | None:
        with self._connect() as c:
            row = c.execute("SELECT * FROM approvals WHERE approval_id=?", (approval_id,)).fetchone()
        return dict(row) if row else None
