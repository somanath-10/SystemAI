from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from systemai.security.redaction import persistence_safe


class AuditLedger:
    """Append-only hash-chained audit ledger.

    This is tamper-evident, not tamper-proof. Production deployments should protect
    the DB with OS permissions and optionally anchor hashes externally.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    task_id TEXT,
                    action_id TEXT,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    prev_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL
                )
                """
            )

    def append(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        task_id: str | None = None,
        action_id: str | None = None,
    ) -> str:
        created_at = datetime.now(timezone.utc).isoformat()
        serialized = json.dumps(persistence_safe(payload), sort_keys=True, separators=(",", ":"), default=str)
        with self._connect() as conn:
            row = conn.execute("SELECT event_hash FROM audit_events ORDER BY seq DESC LIMIT 1").fetchone()
            prev_hash = row["event_hash"] if row else "GENESIS"
            canonical = "|".join([event_type, task_id or "", action_id or "", created_at, prev_hash, serialized])
            event_hash = hashlib.sha256(canonical.encode()).hexdigest()
            conn.execute(
                "INSERT INTO audit_events(event_type,task_id,action_id,payload,created_at,prev_hash,event_hash) VALUES(?,?,?,?,?,?,?)",
                (event_type, task_id, action_id, serialized, created_at, prev_hash, event_hash),
            )
        return event_hash

    def verify_chain(self) -> tuple[bool, int]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM audit_events ORDER BY seq").fetchall()
        prev_hash = "GENESIS"
        for row in rows:
            if row["prev_hash"] != prev_hash:
                return False, int(row["seq"])
            canonical = "|".join([
                row["event_type"],
                row["task_id"] or "",
                row["action_id"] or "",
                row["created_at"],
                row["prev_hash"],
                row["payload"],
            ])
            expected = hashlib.sha256(canonical.encode()).hexdigest()
            if expected != row["event_hash"]:
                return False, int(row["seq"])
            prev_hash = row["event_hash"]
        return True, len(rows)

    def list_events(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM audit_events ORDER BY seq DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) | {"payload": json.loads(row["payload"])} for row in rows]
