import sqlite3
from pathlib import Path

from systemai.memory.audit import AuditLedger


def test_audit_chain_detects_tampering(tmp_path: Path):
    db = tmp_path / "audit.db"
    ledger = AuditLedger(db)
    ledger.append("ONE", {"a": 1})
    ledger.append("TWO", {"b": 2})
    assert ledger.verify_chain() == (True, 2)

    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE audit_events SET payload='{}' WHERE seq=1")
    ok, seq = ledger.verify_chain()
    assert not ok
    assert seq == 1
