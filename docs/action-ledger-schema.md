# SecureClawAgent — Encrypted Action Ledger DDL

## SQLCipher Database Schema

```sql
-- Enable WAL mode for better concurrent read/write
PRAGMA journal_mode=WAL;

-- Set encryption key (passed at open time, never stored in file)
-- PRAGMA key='user-derived-key';

-- Tune for security over performance
PRAGMA cipher_page_size=4096;
PRAGMA kdf_iter=256000;
PRAGMA cipher_hmac_algorithm=HMAC_SHA512;
PRAGMA cipher_kdf_algorithm=PBKDF2_HMAC_SHA512;

-- Core action ledger table
CREATE TABLE IF NOT EXISTS action_ledger (
    id                  TEXT PRIMARY KEY,
    action_id           TEXT NOT NULL,
    task_id             TEXT NOT NULL,
    action_type         TEXT NOT NULL,
    pre_state_hash      TEXT NOT NULL,
    post_state_hash     TEXT,
    diff                TEXT,
    inverse_action      TEXT NOT NULL,   /* JSON */
    hmac_signature      TEXT,
    created_at          TEXT NOT NULL,   /* ISO-8601 */
    reverted            INTEGER DEFAULT 0,
    reverted_at         TEXT
);

-- Task metadata table
CREATE TABLE IF NOT EXISTS tasks (
    id                  TEXT PRIMARY KEY,
    instruction         TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'pending',
    subtasks_json       TEXT,            /* JSON array */
    created_at          TEXT NOT NULL,
    completed_at        TEXT,
    token_usage         INTEGER DEFAULT 0,
    token_budget        INTEGER DEFAULT 100000,
    error_message       TEXT
);

-- User table (for multi-user deployments)
CREATE TABLE IF NOT EXISTS users (
    id                  TEXT PRIMARY KEY,
    username            TEXT NOT NULL UNIQUE,
    password_hash       TEXT NOT NULL,
    salt                BLOB NOT NULL,
    totp_secret         TEXT,
    totp_enabled        INTEGER DEFAULT 0,
    created_at          TEXT NOT NULL
);

-- User sessions (for server restarts — normally sessions are memory-only)
CREATE TABLE IF NOT EXISTS sessions (
    token               TEXT PRIMARY KEY,
    user_id             TEXT NOT NULL,
    created_at          TEXT NOT NULL,
    expires_at          TEXT NOT NULL,
    ip_address          TEXT
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_ledger_task ON action_ledger(task_id);
CREATE INDEX IF NOT EXISTS idx_ledger_action ON action_ledger(action_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
```

## Table Design Notes

### action_ledger
- **id**: UUID v4, generated at snapshot time
- **action_id**: Foreign reference to the `ActionRecord.id` in the runtime model
- **inverse_action**: JSON-serialized `InverseActionDescriptor` with keys:
  - `action_type`: `"file_restore"` | `"undo_script"` | `"compensating_api"` | `"manual_required"`
  - `description`: Human-readable summary of what the revert will do
  - `payload`: Dict of revert parameters (file paths, script content, API endpoint)
- **hmac_signature**: HMAC-SHA256 over `(action_id, task_id, pre_state_hash, inverse_action_json)` — prevents tampering

### tasks
- **subtasks_json**: Serialized list of Subtask Pydantic models (reconstituted at read time)

### users
- **password_hash**: Argon2id hash output (includes salt, params embedded)
- **salt**: Separate stored salt for key derivation (master encryption key)
- **totp_secret**: Base32 secret for TOTP generation

### sessions
- Sessions are **normally memory-only** for security, but this table exists for server restart scenarios. When enabled, session tokens stored here are encrypted with the same AES-256-GCM key as all other data.

## Integrity Verification

Every ledger entry is integrity-protected by HMAC-SHA256:

```
hmac = HMAC-SHA256(
    key = hmac_signing_key (derived from master key),
    message = action_id || "|" || task_id || "|" || pre_state_hash || "|" || inverse_action_json
)
```

The HMAC key is derived from the master encryption key but is a separate sub-key:
- Master key → HKDF-SHA256(expand) → HMAC signing key
- This ensures that compromising the HMAC key doesn't compromise the encryption key

## Export Format (JSON Lines)

For compliance/audit exports:

```jsonl
{"id":"ledger_abc","action_id":"action_abc","task_id":"task_xyz","action_type":"file_write","pre_state_hash":"sha256_abc123...","post_state_hash":"sha256_def456...","diff":"@@ -1,3 +1,4 @@ ...","inverse_action":{"action_type":"file_restore","description":"Restore main.py from snapshot","payload":{"file":"main.py","snapshot_hash":"sha256_abc123..."}},"hmac_signature":"hex_hmac...","timestamp":"2026-06-08T12:00:00Z"}
```

Each line is self-contained and independently verifiable via its HMAC signature.
