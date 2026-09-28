from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


class EventStore:
    """SQLite/WAL append-only source of truth for runtime events.

    The store also contains compact projections/action-journal tables. Events are
    hash chained so accidental or unauthorized historical edits are detectable.
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def _init_schema(self) -> None:
        with self.connect() as c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS events(
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    event_type TEXT NOT NULL,
                    task_id TEXT,
                    node_id TEXT,
                    action_id TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    previous_hash TEXT,
                    event_hash TEXT NOT NULL UNIQUE
                );
                CREATE INDEX IF NOT EXISTS idx_events_task ON events(task_id, sequence);
                CREATE INDEX IF NOT EXISTS idx_events_action ON events(action_id, sequence);

                CREATE TABLE IF NOT EXISTS tasks(
                    task_id TEXT PRIMARY KEY,
                    goal_id TEXT NOT NULL,
                    objective TEXT NOT NULL,
                    state TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS task_nodes(
                    task_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(task_id, node_id)
                );
                CREATE TABLE IF NOT EXISTS task_edges(
                    task_id TEXT NOT NULL,
                    from_node TEXT NOT NULL,
                    to_node TEXT NOT NULL,
                    PRIMARY KEY(task_id, from_node, to_node)
                );
                CREATE TABLE IF NOT EXISTS action_journal(
                    action_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    node_id TEXT,
                    status TEXT NOT NULL,
                    intent_json TEXT NOT NULL,
                    result_json TEXT,
                    token_nonce TEXT,
                    idempotency_key TEXT,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS verification_results(
                    action_id TEXT PRIMARY KEY,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS resource_leases(
                    resource TEXT PRIMARY KEY,
                    lease_id TEXT NOT NULL UNIQUE,
                    holder_task_id TEXT NOT NULL,
                    holder_node_id TEXT,
                    fencing_token INTEGER NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS lease_sequence(
                    id INTEGER PRIMARY KEY CHECK(id=1),
                    value INTEGER NOT NULL
                );
                INSERT OR IGNORE INTO lease_sequence(id, value) VALUES(1, 0);
                CREATE TABLE IF NOT EXISTS used_capability_nonces(
                    nonce TEXT PRIMARY KEY,
                    action_id TEXT NOT NULL,
                    used_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS model_calls(
                    call_id TEXT PRIMARY KEY,
                    task_id TEXT,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    input_tokens INTEGER DEFAULT 0,
                    output_tokens INTEGER DEFAULT 0,
                    images INTEGER DEFAULT 0,
                    audio_seconds REAL DEFAULT 0,
                    estimated_cost_usd REAL DEFAULT 0,
                    latency_ms REAL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS artifacts(
                    artifact_id TEXT PRIMARY KEY,
                    task_id TEXT,
                    kind TEXT NOT NULL,
                    path TEXT,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS projection_checkpoints(
                    projection TEXT PRIMARY KEY,
                    last_sequence INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def append(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
        *,
        task_id: str | None = None,
        node_id: str | None = None,
        action_id: str | None = None,
    ) -> dict[str, Any]:
        payload = payload or {}
        event_id = f"evt_{uuid4().hex[:16]}"
        created_at = _now()
        payload_json = _canonical(payload)
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            prev = c.execute("SELECT event_hash FROM events ORDER BY sequence DESC LIMIT 1").fetchone()
            previous_hash = prev["event_hash"] if prev else None
            material = _canonical(
                {
                    "event_id": event_id,
                    "event_type": event_type,
                    "task_id": task_id,
                    "node_id": node_id,
                    "action_id": action_id,
                    "payload": payload,
                    "created_at": created_at,
                    "previous_hash": previous_hash,
                }
            )
            event_hash = hashlib.sha256(material.encode()).hexdigest()
            cur = c.execute(
                """
                INSERT INTO events(event_id,event_type,task_id,node_id,action_id,payload_json,created_at,previous_hash,event_hash)
                VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (event_id, event_type, task_id, node_id, action_id, payload_json, created_at, previous_hash, event_hash),
            )
            sequence = int(cur.lastrowid)
        return {
            "sequence": sequence,
            "event_id": event_id,
            "event_type": event_type,
            "task_id": task_id,
            "node_id": node_id,
            "action_id": action_id,
            "payload": payload,
            "created_at": created_at,
            "previous_hash": previous_hash,
            "event_hash": event_hash,
        }

    def list_events(self, *, task_id: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
        limit = min(max(int(limit), 1), 1_000)
        sql = "SELECT * FROM events"
        args: list[Any] = []
        if task_id:
            sql += " WHERE task_id=?"
            args.append(task_id)
        sql += " ORDER BY sequence ASC LIMIT ?"
        args.append(limit)
        with self.connect() as c:
            rows = c.execute(sql, args).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            d["payload"] = json.loads(d.pop("payload_json"))
            out.append(d)
        return out

    def verify_chain(self) -> bool:
        prev_hash: str | None = None
        with self.connect() as c:
            rows = c.execute("SELECT * FROM events ORDER BY sequence ASC").fetchall()
        for r in rows:
            payload = json.loads(r["payload_json"])
            material = _canonical(
                {
                    "event_id": r["event_id"],
                    "event_type": r["event_type"],
                    "task_id": r["task_id"],
                    "node_id": r["node_id"],
                    "action_id": r["action_id"],
                    "payload": payload,
                    "created_at": r["created_at"],
                    "previous_hash": prev_hash,
                }
            )
            expected = hashlib.sha256(material.encode()).hexdigest()
            if r["previous_hash"] != prev_hash or r["event_hash"] != expected:
                return False
            prev_hash = r["event_hash"]
        return True

    def upsert_task(self, task_id: str, goal_id: str, objective: str, state: str, snapshot: dict[str, Any]) -> None:
        with self.connect() as c:
            c.execute(
                """
                INSERT INTO tasks(task_id,goal_id,objective,state,snapshot_json,updated_at)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(task_id) DO UPDATE SET state=excluded.state,snapshot_json=excluded.snapshot_json,updated_at=excluded.updated_at
                """,
                (task_id, goal_id, objective, state, _canonical(snapshot), _now()),
            )

    def task_snapshots(self) -> list[dict[str, Any]]:
        with self.connect() as c:
            rows = c.execute("SELECT task_id,snapshot_json FROM tasks ORDER BY updated_at,task_id").fetchall()
        return [{"task_id": row["task_id"], "snapshot": json.loads(row["snapshot_json"])} for row in rows]

    def upsert_node(self, task_id: str, node_id: str, state: str, payload: dict[str, Any]) -> None:
        with self.connect() as c:
            c.execute(
                """
                INSERT INTO task_nodes(task_id,node_id,state,payload_json,updated_at)
                VALUES(?,?,?,?,?)
                ON CONFLICT(task_id,node_id) DO UPDATE SET state=excluded.state,payload_json=excluded.payload_json,updated_at=excluded.updated_at
                """,
                (task_id, node_id, state, _canonical(payload), _now()),
            )

    def replace_edges(self, task_id: str, edges: Iterable[tuple[str, str]]) -> None:
        with self.connect() as c:
            c.execute("DELETE FROM task_edges WHERE task_id=?", (task_id,))
            c.executemany("INSERT INTO task_edges(task_id,from_node,to_node) VALUES(?,?,?)", [(task_id, a, b) for a, b in edges])

    def mark_nonce_used(self, nonce: str, action_id: str) -> bool:
        try:
            with self.connect() as c:
                c.execute("INSERT INTO used_capability_nonces VALUES(?,?,?)", (nonce, action_id, _now()))
            return True
        except sqlite3.IntegrityError:
            return False
