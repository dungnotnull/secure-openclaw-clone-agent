from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backend.core.models.ledger import (
    InverseActionDescriptor,
    InverseActionType,
    LedgerEntry,
)

SCHEMA = r"""
CREATE TABLE IF NOT EXISTS action_ledger (
    id           TEXT PRIMARY KEY,
    action_id    TEXT NOT NULL,
    task_id      TEXT NOT NULL,
    action_type  TEXT NOT NULL,
    pre_state_hash   TEXT NOT NULL,
    post_state_hash  TEXT,
    diff              TEXT,
    inverse_action   TEXT NOT NULL,   /* JSON */
    hmac_signature   TEXT,
    created_at       TEXT NOT NULL,   /* ISO-8601 */
    reverted         INTEGER DEFAULT 0,
    reverted_at      TEXT
);

CREATE INDEX IF NOT EXISTS idx_ledger_task
    ON action_ledger(task_id);

CREATE INDEX IF NOT EXISTS idx_ledger_action
    ON action_ledger(action_id);
"""


class ActionLedger:
    """Encrypted SQLite ledger for recording every action's pre/post state
    and its inverse-action descriptor.  HMAC-SHA256 ensures integrity."""

    def __init__(self, db_path: str | Path, hmac_key: bytes) -> None:
        self._db_path = str(db_path)
        self._hmac_key = hmac_key
        self._conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    def open(self, pragma_key: str | None = None) -> None:
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        if pragma_key:
            self._conn.execute(f"PRAGMA key='{pragma_key}'")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def insert(self, entry: LedgerEntry) -> LedgerEntry:
        if entry.hmac_signature is None:
            entry.hmac_signature = self._compute_hmac(entry)
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT INTO action_ledger
               (id, action_id, task_id, action_type, pre_state_hash,
                post_state_hash, diff, inverse_action, hmac_signature, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry.id,
                entry.action_id,
                entry.task_id,
                entry.action_type,
                entry.pre_state_hash,
                entry.post_state_hash,
                entry.diff,
                entry.inverse_action.model_dump_json(),
                entry.hmac_signature,
                now,
            ),
        )
        self._conn.commit()
        return entry

    def get_by_action(self, action_id: str) -> Optional[LedgerEntry]:
        row = self._conn.execute(
            "SELECT * FROM action_ledger WHERE action_id = ? ORDER BY created_at DESC LIMIT 1",
            (action_id,),
        ).fetchone()
        return self._row_to_entry(row) if row else None

    def get_by_task(self, task_id: str) -> list[LedgerEntry]:
        rows = self._conn.execute(
            "SELECT * FROM action_ledger WHERE task_id = ? ORDER BY created_at ASC",
            (task_id,),
        ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def mark_reverted(self, action_id: str) -> None:
        self._conn.execute(
            "UPDATE action_ledger SET reverted=1, reverted_at=? WHERE action_id=?",
            (datetime.now(timezone.utc).isoformat(), action_id),
        )
        self._conn.commit()

    def verify_hmac(self, entry: LedgerEntry) -> bool:
        if entry.hmac_signature is None:
            return False
        return hmac.compare_digest(entry.hmac_signature, self._compute_hmac(entry))

    def export_jsonl(self, task_id: str) -> str:
        entries = self.get_by_task(task_id)
        lines = []
        for e in entries:
            record = {
                "id": e.id,
                "action_id": e.action_id,
                "task_id": e.task_id,
                "action_type": e.action_type,
                "pre_state_hash": e.pre_state_hash,
                "post_state_hash": e.post_state_hash,
                "diff": e.diff,
                "inverse_action": e.inverse_action.model_dump(),
                "hmac_signature": e.hmac_signature,
                "timestamp": e.timestamp.isoformat(),
            }
            lines.append(json.dumps(record, ensure_ascii=False))
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------
    def _compute_hmac(self, entry: LedgerEntry) -> str:
        payload = f"{entry.action_id}|{entry.task_id}|{entry.pre_state_hash}|{entry.inverse_action.model_dump_json()}"
        return hmac.new(self._hmac_key, payload.encode(), hashlib.sha256).hexdigest()

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> LedgerEntry:
        inv = json.loads(row["inverse_action"])
        return LedgerEntry(
            id=row["id"],
            action_id=row["action_id"],
            task_id=row["task_id"],
            action_type=row["action_type"],
            pre_state_hash=row["pre_state_hash"],
            post_state_hash=row["post_state_hash"],
            diff=row["diff"],
            inverse_action=InverseActionDescriptor(**inv),
            hmac_signature=row["hmac_signature"],
            timestamp=datetime.fromisoformat(row["created_at"]),
            reverted=bool(row["reverted"]),
            reverted_at=datetime.fromisoformat(row["reverted_at"]) if row["reverted_at"] else None,
        )
