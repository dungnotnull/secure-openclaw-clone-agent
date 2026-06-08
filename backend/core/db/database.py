from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backend.core.config import settings
from backend.core.models.user import User, UserSession
from backend.core.models.task import Task, Subtask, TaskStatus
from backend.core.models.ledger import LedgerEntry, InverseActionDescriptor

SCHEMA = r"""
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    salt          BLOB NOT NULL,
    totp_secret   TEXT,
    totp_enabled  INTEGER DEFAULT 0,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token         TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    expires_at    TEXT NOT NULL,
    ip_address    TEXT
);

CREATE TABLE IF NOT EXISTS tasks (
    id            TEXT PRIMARY KEY,
    instruction   TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending',
    subtasks_json TEXT,
    created_at    TEXT NOT NULL,
    completed_at  TEXT,
    token_usage   INTEGER DEFAULT 0,
    token_budget  INTEGER DEFAULT 100000,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS action_ledger (
    id              TEXT PRIMARY KEY,
    action_id       TEXT NOT NULL,
    task_id         TEXT NOT NULL,
    action_type     TEXT NOT NULL,
    pre_state_hash  TEXT NOT NULL,
    post_state_hash TEXT,
    diff            TEXT,
    inverse_action  TEXT NOT NULL,
    hmac_signature  TEXT,
    created_at      TEXT NOT NULL,
    reverted        INTEGER DEFAULT 0,
    reverted_at     TEXT
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_ledger_task ON action_ledger(task_id);
CREATE INDEX IF NOT EXISTS idx_ledger_action ON action_ledger(action_id);
"""


class Database:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = str(db_path or settings.DB_PATH)
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    def open(self, pragma_key: str | None = None) -> None:
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        if pragma_key:
            self._conn.execute(f"PRAGMA key='{pragma_key}'")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Database not opened. Call db.open() first.")
        return self._conn

    def execute(self, sql: str, params=()) -> sqlite3.Cursor:
        return self.conn.execute(sql, params)

    def commit(self) -> None:
        self.conn.commit()

    # --- User CRUD ---
    def create_user(self, user: User) -> User:
        self.execute(
            "INSERT INTO users (id, username, password_hash, salt, totp_secret, totp_enabled, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user.id, user.username, user.password_hash, user.salt,
             user.totp_secret, int(user.totp_enabled), user.created_at.isoformat()),
        )
        self.commit()
        return user

    def get_user_by_username(self, username: str) -> Optional[User]:
        row = self.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if not row:
            return None
        return User(
            id=row["id"], username=row["username"],
            password_hash=row["password_hash"], salt=bytes(row["salt"]),
            totp_secret=row["totp_secret"], totp_enabled=bool(row["totp_enabled"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        row = self.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if not row:
            return None
        return User(
            id=row["id"], username=row["username"],
            password_hash=row["password_hash"], salt=bytes(row["salt"]),
            totp_secret=row["totp_secret"], totp_enabled=bool(row["totp_enabled"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    # --- Session CRUD ---
    def create_session(self, session: UserSession) -> UserSession:
        self.execute(
            "INSERT INTO sessions (token, user_id, created_at, expires_at, ip_address) "
            "VALUES (?, ?, ?, ?, ?)",
            (session.token, session.user_id, session.created_at.isoformat(),
             session.expires_at.isoformat(), session.ip_address),
        )
        self.commit()
        return session

    def get_session(self, token: str) -> Optional[UserSession]:
        row = self.execute("SELECT * FROM sessions WHERE token=?", (token,)).fetchone()
        if not row:
            return None
        return UserSession(
            token=row["token"], user_id=row["user_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            expires_at=datetime.fromisoformat(row["expires_at"]),
            ip_address=row["ip_address"],
        )

    def delete_session(self, token: str) -> None:
        self.execute("DELETE FROM sessions WHERE token=?", (token,))
        self.commit()

    def cleanup_expired_sessions(self) -> int:
        now = datetime.now(timezone.utc).isoformat()
        c = self.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
        self.commit()
        return c.rowcount

    # --- Task CRUD ---
    def create_task(self, task: Task) -> Task:
        self.execute(
            "INSERT INTO tasks (id, instruction, status, subtasks_json, created_at, "
            "completed_at, token_usage, token_budget, error_message) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (task.id, task.instruction, task.status.value,
             json.dumps([s.model_dump() for s in task.subtasks]),
             task.created_at.isoformat(), task.completed_at.isoformat() if task.completed_at else None,
             task.token_usage, task.token_budget, task.error_message),
        )
        self.commit()
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        row = self.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            return None
        return self._row_to_task(row)

    def list_tasks(self, limit: int = 50, offset: int = 0) -> list[Task]:
        rows = self.execute(
            "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [self._row_to_task(r) for r in rows]

    def update_task(self, task: Task) -> Task:
        self.execute(
            "UPDATE tasks SET status=?, subtasks_json=?, completed_at=?, "
            "token_usage=?, error_message=? WHERE id=?",
            (task.status.value,
             json.dumps([s.model_dump() for s in task.subtasks]),
             task.completed_at.isoformat() if task.completed_at else None,
             task.token_usage, task.error_message, task.id),
        )
        self.commit()
        return task

    # --- Ledger CRUD ---
    def insert_ledger_entry(self, entry: LedgerEntry) -> LedgerEntry:
        self.execute(
            "INSERT INTO action_ledger (id, action_id, task_id, action_type, "
            "pre_state_hash, post_state_hash, diff, inverse_action, hmac_signature, "
            "created_at, reverted, reverted_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (entry.id, entry.action_id, entry.task_id, entry.action_type,
             entry.pre_state_hash, entry.post_state_hash, entry.diff,
             entry.inverse_action.model_dump_json(), entry.hmac_signature,
             entry.timestamp.isoformat(), int(entry.reverted),
             entry.reverted_at.isoformat() if entry.reverted_at else None),
        )
        self.commit()
        return entry

    def get_ledger_by_action(self, action_id: str) -> Optional[LedgerEntry]:
        row = self.execute(
            "SELECT * FROM action_ledger WHERE action_id=? ORDER BY created_at DESC LIMIT 1",
            (action_id,),
        ).fetchone()
        if not row:
            return None
        return self._row_to_ledger(row)

    def get_ledger_by_task(self, task_id: str) -> list[LedgerEntry]:
        rows = self.execute(
            "SELECT * FROM action_ledger WHERE task_id=? ORDER BY created_at ASC",
            (task_id,),
        ).fetchall()
        return [self._row_to_ledger(r) for r in rows]

    def mark_ledger_reverted(self, action_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.execute(
            "UPDATE action_ledger SET reverted=1, reverted_at=? WHERE action_id=?",
            (now, action_id),
        )
        self.commit()

    def export_ledger_jsonl(self, task_id: str) -> str:
        entries = self.get_ledger_by_task(task_id)
        lines = []
        for e in entries:
            record = {
                "id": e.id, "action_id": e.action_id, "task_id": e.task_id,
                "action_type": e.action_type, "pre_state_hash": e.pre_state_hash,
                "post_state_hash": e.post_state_hash, "diff": e.diff,
                "inverse_action": e.inverse_action.model_dump(),
                "hmac_signature": e.hmac_signature,
                "timestamp": e.timestamp.isoformat(),
            }
            lines.append(json.dumps(record, ensure_ascii=False))
        return "\n".join(lines)

    @staticmethod
    def _row_to_task(row: sqlite3.Row) -> Task:
        subtasks_raw = json.loads(row["subtasks_json"]) if row["subtasks_json"] else []
        return Task(
            id=row["id"], instruction=row["instruction"],
            status=TaskStatus(row["status"]),
            subtasks=[Subtask(**s) for s in subtasks_raw],
            created_at=datetime.fromisoformat(row["created_at"]),
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            token_usage=row["token_usage"], token_budget=row["token_budget"],
            error_message=row["error_message"],
        )

    @staticmethod
    def _row_to_ledger(row: sqlite3.Row) -> LedgerEntry:
        inv = json.loads(row["inverse_action"])
        return LedgerEntry(
            id=row["id"], action_id=row["action_id"], task_id=row["task_id"],
            action_type=row["action_type"], pre_state_hash=row["pre_state_hash"],
            post_state_hash=row["post_state_hash"], diff=row["diff"],
            inverse_action=InverseActionDescriptor(**inv),
            hmac_signature=row["hmac_signature"],
            timestamp=datetime.fromisoformat(row["created_at"]),
            reverted=bool(row["reverted"]),
            reverted_at=datetime.fromisoformat(row["reverted_at"]) if row["reverted_at"] else None,
        )


_db_instance: Database | None = None


def get_db() -> Database:
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
        _db_instance.open(pragma_key=settings.DB_PRAGMA_KEY or None)
    return _db_instance
