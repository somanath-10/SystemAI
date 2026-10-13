from __future__ import annotations

import hashlib
import json
import math
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

    def __init__(self, db_path: Path, *, read_only: bool = False) -> None:
        self.db_path = Path(db_path)
        self.read_only = read_only
        if not read_only:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._init_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path.resolve().as_uri() + "?mode=ro", uri=True, timeout=30) if self.read_only else sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        if not self.read_only:
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
                    kind TEXT NOT NULL DEFAULT 'local_small',
                    input_tokens INTEGER DEFAULT 0,
                    output_tokens INTEGER DEFAULT 0,
                    images INTEGER DEFAULT 0,
                    audio_seconds REAL DEFAULT 0,
                    estimated_cost_usd REAL DEFAULT 0,
                    latency_ms REAL DEFAULT 0,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
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
                CREATE TABLE IF NOT EXISTS monitor_rules(
                    rule_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    process_name TEXT NOT NULL,
                    cooldown_seconds INTEGER NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    last_fired_at TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS semantic_notes(
                    note_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL REFERENCES tasks(task_id),
                    content TEXT NOT NULL CHECK(length(content) BETWEEN 1 AND 4000),
                    model_digest TEXT NOT NULL,
                    vector_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_semantic_notes_task_model ON semantic_notes(task_id,model_digest);
                """
            )
            columns = {row[1] for row in c.execute("PRAGMA table_info(model_calls)")}
            if "kind" not in columns:
                c.execute("ALTER TABLE model_calls ADD COLUMN kind TEXT NOT NULL DEFAULT 'local_small'")
            if "metadata_json" not in columns:
                c.execute("ALTER TABLE model_calls ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}'")

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

    def list_events(self, *, task_id: str | None = None, limit: int = 500, latest: bool = False) -> list[dict[str, Any]]:
        limit = min(max(int(limit), 1), 1_000)
        sql = "SELECT * FROM events"
        args: list[Any] = []
        if task_id:
            sql += " WHERE task_id=?"
            args.append(task_id)
        sql += " ORDER BY sequence " + ("DESC" if latest else "ASC") + " LIMIT ?"
        args.append(limit)
        with self.connect() as c:
            rows = c.execute(sql, args).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            d["payload"] = json.loads(d.pop("payload_json"))
            out.append(d)
        return out

    def latest_skill_review(self, task_id: str) -> dict[str, Any] | None:
        with self.connect() as c:
            row = c.execute(
                "SELECT payload_json, created_at FROM events WHERE task_id=? AND event_type='SkillCandidateReviewRecorded' ORDER BY sequence DESC LIMIT 1",
                (task_id,),
            ).fetchone()
        return {**json.loads(row["payload_json"]), "recorded_at": row["created_at"]} if row else None

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

    def record_model_call(self, record: dict[str, Any]) -> None:
        with self.connect() as c:
            self._insert_model_call(c, record)

    @staticmethod
    def _insert_model_call(c: sqlite3.Connection, record: dict[str, Any]) -> None:
        c.execute(
                """
                INSERT INTO model_calls(
                    call_id,task_id,provider,model,kind,input_tokens,output_tokens,
                    images,audio_seconds,estimated_cost_usd,latency_ms,metadata_json,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    record["call_id"], record["task_id"], record["provider"], record["model"] or "",
                    record["kind"], record["input_tokens"], record["output_tokens"], record["image_count"],
                    record["audio_seconds"], record["estimated_cost_usd"], record.get("latency_ms", 0.0),
                    _canonical(record.get("metadata", {})), record["created_at"],
                ),
        )

    def reserve_external_model_call(self, record: dict[str, Any], *, max_cost: float, max_calls: int,
                                    max_vision_calls: int, max_audio_seconds: float = 120,
                                    active_calls: tuple[str, ...] = ()) -> str | None:
        """Atomically hold budget across processes before an external request."""
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            rows = c.execute(
                """SELECT call_id,estimated_cost_usd,images,audio_seconds,metadata_json FROM model_calls
                   WHERE task_id=? AND kind IN ('specialist_api','standard_api','premium_api')""",
                (record["task_id"],),
            ).fetchall()
            active = set(active_calls)
            uncertain = any(json.loads(row["metadata_json"]).get("billing_state") == "overrun" or
                            (json.loads(row["metadata_json"]).get("billing_state") == "reserved" and row["call_id"] not in active)
                            for row in rows)
            reason = (
                "previous external charge is unresolved" if uncertain else
                "external call budget exhausted" if len(rows) + 1 > max_calls else
                "external dollar budget exhausted" if sum(row["estimated_cost_usd"] for row in rows) + record["estimated_cost_usd"] > max_cost + 1e-12 else
                "external vision-call budget exhausted" if record["image_count"] and sum(row["images"] > 0 for row in rows) + 1 > max_vision_calls else
                "external audio budget exhausted" if sum(row["audio_seconds"] for row in rows) + record["audio_seconds"] > max_audio_seconds else None
            )
            if reason is None:
                self._insert_model_call(c, record)
            return reason

    def settle_external_model_call(self, call_id: str, *, input_tokens: int, output_tokens: int,
                                   estimated_cost_usd: float, latency_ms: float) -> bool:
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT estimated_cost_usd,metadata_json FROM model_calls WHERE call_id=?", (call_id,)).fetchone()
            if row is None or json.loads(row["metadata_json"]).get("billing_state") != "reserved":
                raise ValueError("external reservation is missing or already settled")
            overrun = estimated_cost_usd > row["estimated_cost_usd"] + 1e-12
            metadata = json.loads(row["metadata_json"])
            metadata["billing_state"] = "overrun" if overrun else "settled"
            c.execute(
                "UPDATE model_calls SET input_tokens=?,output_tokens=?,estimated_cost_usd=?,latency_ms=?,metadata_json=? WHERE call_id=?",
                (input_tokens, output_tokens, estimated_cost_usd, latency_ms, _canonical(metadata), call_id),
            )
            return overrun

    def has_unsettled_external(self, task_id: str, *, active_calls: tuple[str, ...] = ()) -> bool:
        with self.connect() as c:
            rows = c.execute(
                """SELECT call_id,metadata_json FROM model_calls WHERE task_id=? AND
                   json_extract(metadata_json,'$.billing_state') IN ('reserved','overrun')""", (task_id,),
            ).fetchall()
        active = set(active_calls)
        return any(row["call_id"] not in active or json.loads(row["metadata_json"])["billing_state"] == "overrun" for row in rows)

    def model_calls_for(self, task_id: str) -> list[dict[str, Any]]:
        with self.connect() as c:
            rows = c.execute("SELECT * FROM model_calls WHERE task_id=? ORDER BY created_at,call_id", (task_id,)).fetchall()
        return [dict(row) | {"metadata": json.loads(row["metadata_json"])} for row in rows]

    def add_monitor_rule(self, event_type: str, process_name: str, cooldown_seconds: int) -> dict[str, Any]:
        rule_id = f"rule_{uuid4().hex[:16]}"
        with self.connect() as c:
            c.execute("INSERT INTO monitor_rules(rule_id,event_type,process_name,cooldown_seconds,created_at) VALUES(?,?,?,?,?)",
                      (rule_id, event_type, process_name, cooldown_seconds, _now()))
        return {"rule_id": rule_id, "event_type": event_type, "process_name": process_name,
                "cooldown_seconds": cooldown_seconds, "enabled": True}

    def monitor_rules(self) -> list[dict[str, Any]]:
        with self.connect() as c:
            rows = c.execute("SELECT * FROM monitor_rules ORDER BY created_at,rule_id").fetchall()
        return [dict(row) | {"enabled": bool(row["enabled"])} for row in rows]

    def set_monitor_rule_enabled(self, rule_id: str, enabled: bool) -> bool:
        with self.connect() as c:
            updated = c.execute("UPDATE monitor_rules SET enabled=? WHERE rule_id=?", (int(enabled), rule_id)).rowcount
        return bool(updated)

    def match_monitor_rules(self, event_type: str, process_name: str) -> list[str]:
        """Claim matching alerts transactionally so concurrent events respect cooldown."""
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        matched: list[str] = []
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            rows = c.execute("SELECT rule_id,cooldown_seconds,last_fired_at FROM monitor_rules WHERE enabled=1 AND event_type=? AND process_name=?",
                             (event_type, process_name)).fetchall()
            for row in rows:
                previous = datetime.fromisoformat(row["last_fired_at"]) if row["last_fired_at"] else None
                if previous is not None and now - previous < timedelta(seconds=row["cooldown_seconds"]):
                    continue
                c.execute("UPDATE monitor_rules SET last_fired_at=? WHERE rule_id=?", (now.isoformat(), row["rule_id"]))
                matched.append(row["rule_id"])
        return matched

    def add_semantic_note(self, task_id: str, content: str, model_digest: str, vector: list[float]) -> str:
        note_id = f"mem_{uuid4().hex[:16]}"
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            count = c.execute("SELECT count(*) FROM semantic_notes WHERE task_id=?", (task_id,)).fetchone()[0]
            if count >= 500:
                raise ValueError("task memory limit reached (500 notes)")
            c.execute("INSERT INTO semantic_notes(note_id,task_id,content,model_digest,vector_json,created_at) VALUES(?,?,?,?,?,?)",
                      (note_id, task_id, content, model_digest, _canonical(vector), _now()))
        return note_id

    def search_semantic_notes(self, task_id: str, model_digest: str, query: list[float], limit: int) -> list[dict[str, Any]]:
        # ponytail: linear scan is bounded to 500 notes/task; use sqlite-vec if that ceiling becomes real.
        with self.connect() as c:
            rows = c.execute("SELECT note_id,content,vector_json FROM semantic_notes WHERE task_id=? AND model_digest=? LIMIT 500",
                             (task_id, model_digest)).fetchall()
        query_norm = math.sqrt(sum(value * value for value in query))
        if not query_norm:
            raise ValueError("query embedding is empty")
        matches = []
        for row in rows:
            vector = json.loads(row["vector_json"])
            if len(vector) != len(query):
                continue
            norm = math.sqrt(sum(value * value for value in vector))
            if norm:
                score = sum(a * b for a, b in zip(vector, query)) / (norm * query_norm)
                matches.append({"note_id": row["note_id"], "content": row["content"], "score": score})
        return sorted(matches, key=lambda item: item["score"], reverse=True)[:limit]

    def delete_semantic_note(self, task_id: str, note_id: str) -> bool:
        with self.connect() as c:
            return bool(c.execute("DELETE FROM semantic_notes WHERE task_id=? AND note_id=?", (task_id, note_id)).rowcount)
