from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable
from uuid import uuid4

from systemai.contracts.models import ResourceLease
from systemai.orchestration.event_store import EventStore


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ResourceBusy(RuntimeError):
    pass


class ResourceLeaseManager:
    """Crash-tolerant lease manager with TTLs and monotonically increasing fences."""

    def __init__(self, store: EventStore) -> None:
        self.store = store

    def acquire_many(self, resources: Iterable[str], *, task_id: str, node_id: str | None, ttl_seconds: int = 30) -> list[ResourceLease]:
        if ttl_seconds <= 0:
            raise ValueError("lease TTL must be positive")
        resources = sorted(set(resources))  # global ordering prevents lock-order deadlocks
        if not resources:
            return []
        now = _now()
        expires = now + timedelta(seconds=ttl_seconds)
        leases: list[ResourceLease] = []
        with self.store.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute("DELETE FROM resource_leases WHERE expires_at <= ?", (now.isoformat(),))
            placeholders = ",".join("?" for _ in resources)
            conflicts = c.execute(f"SELECT resource,holder_task_id,holder_node_id FROM resource_leases WHERE resource IN ({placeholders})", resources).fetchall()
            if conflicts:
                raise ResourceBusy(", ".join(f"{x['resource']} held by {x['holder_task_id']}" for x in conflicts))
            seq = c.execute("SELECT value FROM lease_sequence WHERE id=1").fetchone()["value"]
            for resource in resources:
                seq += 1
                lease = ResourceLease(
                    resource=resource,
                    holder_task_id=task_id,
                    holder_node_id=node_id,
                    lease_id=f"lease_{uuid4().hex[:16]}",
                    fencing_token=seq,
                    expires_at=expires,
                )
                c.execute(
                    "INSERT INTO resource_leases(resource,lease_id,holder_task_id,holder_node_id,fencing_token,expires_at,created_at) VALUES(?,?,?,?,?,?,?)",
                    (resource, lease.lease_id, task_id, node_id, lease.fencing_token, expires.isoformat(), now.isoformat()),
                )
                leases.append(lease)
            c.execute("UPDATE lease_sequence SET value=? WHERE id=1", (seq,))
        for lease in leases:
            self.store.append("ResourceLeaseGranted", lease.model_dump(mode="json"), task_id=task_id, node_id=node_id)
        return leases

    def renew(self, lease_id: str, *, ttl_seconds: int = 30) -> ResourceLease:
        if ttl_seconds <= 0:
            raise ValueError("lease TTL must be positive")
        now = _now()
        expires = now + timedelta(seconds=ttl_seconds)
        with self.store.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT * FROM resource_leases WHERE lease_id=?", (lease_id,)).fetchone()
            if not row:
                raise KeyError(lease_id)
            if _dt(row["expires_at"]) <= now:
                c.execute("DELETE FROM resource_leases WHERE lease_id=?", (lease_id,))
                raise KeyError(lease_id)
            c.execute("UPDATE resource_leases SET expires_at=? WHERE lease_id=?", (expires.isoformat(), lease_id))
        return ResourceLease(
            resource=row["resource"],
            holder_task_id=row["holder_task_id"],
            holder_node_id=row["holder_node_id"],
            lease_id=row["lease_id"],
            fencing_token=row["fencing_token"],
            expires_at=expires,
        )

    def release(self, lease_id: str) -> None:
        with self.store.connect() as c:
            row = c.execute("SELECT * FROM resource_leases WHERE lease_id=?", (lease_id,)).fetchone()
            if not row:
                return
            c.execute("DELETE FROM resource_leases WHERE lease_id=?", (lease_id,))
        self.store.append("ResourceLeaseReleased", {"lease_id": lease_id, "resource": row["resource"]}, task_id=row["holder_task_id"], node_id=row["holder_node_id"])

    def release_many(self, leases: Iterable[ResourceLease]) -> None:
        for lease in leases:
            self.release(lease.lease_id)

    def list_active(self) -> list[dict]:
        now = _now().isoformat()
        with self.store.connect() as c:
            c.execute("DELETE FROM resource_leases WHERE expires_at <= ?", (now,))
            rows = c.execute("SELECT * FROM resource_leases ORDER BY resource").fetchall()
        return [dict(r) for r in rows]
