from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from systemai.security.redaction import persistence_safe


class MemoryStore:
    """Local episodic/procedural store for tasks and successful trajectories."""

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
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    state TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS trajectories (
                    trajectory_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    goal TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS skills (
                    name TEXT PRIMARY KEY,
                    version INTEGER NOT NULL,
                    payload TEXT NOT NULL
                );
                """
            )

    def put_task(self, task_id: str, goal: str, state: str, payload: dict[str, Any]) -> None:
        data = json.dumps(persistence_safe(payload), default=str)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO tasks(task_id,goal,state,payload) VALUES(?,?,?,?) ON CONFLICT(task_id) DO UPDATE SET state=excluded.state,payload=excluded.payload",
                (task_id, goal, state, data),
            )

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if not row:
            return None
        return dict(row) | {"payload": json.loads(row["payload"])}

    def add_trajectory(self, goal: str, task_id: str, success: bool, payload: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO trajectories(goal,task_id,success,payload) VALUES(?,?,?,?)",
                (goal, task_id, int(success), json.dumps(persistence_safe(payload), default=str)),
            )

    def recent_successes(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM trajectories WHERE success=1 ORDER BY trajectory_id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) | {"payload": json.loads(r["payload"])} for r in rows]
