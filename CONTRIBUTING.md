# Contributing to SecureClawAgent

## Setup

```bash
git clone https://github.com/your-org/secure-openclaw-clone.git
cd secure-openclaw-clone
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd frontend && npm install && cd ..
```

## Development

- Backend code: `backend/core/`
- Frontend code: `frontend/src/`
- Documentation: `docs/`

### Run checks before PR

```bash
# Python lint
pip install ruff && ruff check backend/

# Frontend type check
cd frontend && npx tsc --noEmit && cd ..

# Build Docker images
docker build -f docker/Dockerfile.backend -t secureclaw-api:dev .
docker build -f docker/Dockerfile.frontend -t secureclaw-frontend:dev .
docker build -f docker/Dockerfile.sandbox -t secureclaw-sandbox:dev .
```

## Architecture Guidelines

1. **Security first** — every new tool or action must run inside the sandbox
2. **Encrypt at rest** — all user data must be encrypted before touching disk
3. **No plaintext credentials** — API keys, tokens, and passwords are never persisted unencrypted
4. **Audit everything** — every action goes through the ledger with HMAC integrity
5. **LLM calls go through provider abstraction** — never call external APIs directly

## Module Map

| Module | Path | Purpose |
|--------|------|---------|
| Config | `backend/core/config.py` | Settings from .env |
| Models | `backend/core/models/` | Pydantic data models |
| Encryption | `backend/core/encryption/` | AES-256-GCM + Argon2id |
| Database | `backend/core/db/` | SQLite/SQLCipher ORM |
| Auth | `backend/core/auth/` | JWT + TOTP 2FA |
| LLM | `backend/core/llm/` | Provider abstraction + PII scrub |
| Security | `backend/core/security/` | Injection detector + risk classifier |
| Sandbox | `backend/core/sandbox/` | Docker executor |
| Snapshot | `backend/core/snapshot/` | Git stash + manifest |
| Revert | `backend/core/revert/` | Inverse action engine |
| Orchestrator | `backend/core/orchestrator/` | Task agent loop |
| ML | `backend/core/ml/` | Local planner + code patch + fine-tune |
| Knowledge | `backend/core/knowledge/` | ArXiv crawler + scheduler |

## Code Style

- Python: follow PEP 8, use type hints everywhere
- TypeScript: strict mode, no `any` unless justified
- No comments unless the logic is non-obvious
- All public functions return typed values
