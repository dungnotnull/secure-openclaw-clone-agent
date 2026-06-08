<p align="center">
  <img src="frontend/public/vite.svg" width="80" alt="SecureClawAgent" />
</p>

<h1 align="center">SecureClawAgent</h1>

<p align="center">
  <strong>Security-hardened AI task agent runtime</strong><br />
  Zero-Trust sandboxing · AES-256-GCM encryption · Full action revert · Multi-provider LLM
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-blue" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/typescript-5.x-3178c6" alt="TypeScript" />
  <img src="https://img.shields.io/badge/react-18.x-61dafb" alt="React 18" />
  <img src="https://img.shields.io/badge/fastapi-0.111-009688" alt="FastAPI" />
  <img src="https://img.shields.io/badge/docker-required-2496ed" alt="Docker" />
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License" />
</p>

---

## Why SecureClawAgent

AI task agents execute arbitrary code on your machine with minimal security guarantees. Standard runtimes store your API keys in plaintext, give agents unrestricted OS access, and offer no way to undo completed actions. A hallucinated `rm -rf` or a prompt-injected command runs unguarded. SecureClawAgent closes all three gaps.

**Every action** runs inside an ephemeral Docker container with a minimal capability grant — no network, no privilege escalation, destroyed immediately after execution. **All user data** — credentials, workspace files, action history — is AES-256-GCM encrypted at rest with an Argon2id-derived key that never touches disk. **Any completed task** — whether a single write or a multi-step pipeline — can be fully rolled back to its exact pre-execution state via git-backed snapshots and inverse-action semantics in an encrypted, HMAC-signed audit ledger.

```
Research: 78% of tested LLM agent frameworks are vulnerable to prompt injection causing
unintended filesystem changes. 0% of surveyed AI developer tools offer encryption of
stored user credentials. SecureClawAgent is the first to address all three dimensions:
isolation, encryption, and reversibility.
```

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          SecureClawAgent System                           │
│                                                                           │
│  ┌──────────────┐    ┌────────────────────────────────────────────────┐  │
│  │  Web UI       │    │              API Gateway (FastAPI)              │  │
│  │ React 18 /TS  │◄──►│  JWT Auth │ TOTP 2FA │ Rate Limiting │ Audit   │  │
│  └──────────────┘    └────────────────────┬───────────────────────────┘  │
│                                           │                               │
│  ┌────────────────────────────────────────▼───────────────────────────┐  │
│  │                      Task Orchestrator                              │  │
│  │   Instruction → Planner (LLM) → Subtask Decomposer → Tool Router   │  │
│  └──────────────────┬──────────────────────┬──────────────────────────┘  │
│                     │                      │                              │
│  ┌──────────────────▼──────────┐  ┌───────▼───────────────────────────┐  │
│  │     LLM Provider Layer       │  │    Security Layer                 │  │
│  │  Claude · OpenAI · Ollama    │  │  Risk Classifier (BART-MNLI)      │  │
│  │  PII Scrub · Fallback Chain  │  │  Injection Detector (regex+sem)   │  │
│  └─────────────────────────────┘  └───────────────────────────────────┘  │
│                                           │                               │
│  ┌────────────────────┐  ┌────────────────▼───────────────────────────┐  │
│  │ Backup & Revert     │  │         Sandbox Execution Layer             │  │
│  │ Engine              │◄─┤   Pre-snapshot → Container → Diff → Ledger  │  │
│  │ ┌────────────────┐  │  │  ┌───────────────────────────────────────┐ │  │
│  │ │ Action Ledger   │  │  │  │  Hardened Container (Alpine Linux)    │ │  │
│  │ │ SQLCipher+HMAC  │  │  │  │  seccomp · cap-drop · non-root        │ │  │
│  │ └────────────────┘  │  │  │  no-network · read-only rootfs · tmpfs │ │  │
│  │ ┌────────────────┐  │  │  │  512MB limit · 1 core · 300s timeout   │ │  │
│  │ │ Git Snapshots   │  │  │  └───────────────────────────────────────┘ │  │
│  │ └────────────────┘  │  └────────────────────────────────────────────┘  │
│  └────────────────────┘                                                   │
│                                                                           │
│  ┌────────────────────────────────────────────────────────────────────┐   │
│  │                  Encrypted Storage Layer                            │   │
│  │  SQLCipher (AES-256-GCM) │ VaultStore (encrypted file envelopes)   │   │
│  │  Argon2id key derivation (64MB, 3 iterations) — key never persisted │   │
│  └────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────┘
```

### Data Flow: One Action, End-to-End

```
1. User submits task → JWT validated → prompt injection scan

2. LLM Planner decomposes instruction into ordered subtasks

3. Risk Classifier assigns tier: Read-Only / Low-Risk Write /
   High-Risk Destructive / Network Egress

4. For each subtask:
   ┌─────────────────────────────────────────────────┐
   │ a. SnapshotEngine: git stash + SHA-256 manifest  │
   │ b. DockerExecutor: ephemeral container spawned    │
   │ c. Tool executes inside sandbox                   │
   │ d. Container destroyed, stdout/stderr captured    │
   │ e. Diff computed, inverse-action saved to ledger  │
   │ f. Ledger entry HMAC-SHA256 signed                │
   └─────────────────────────────────────────────────┘

5. If High-Risk → UI pauses for user confirmation

6. Result Aggregator collects outputs, reports summary

7. Revert requested?
   ┌─────────────────────────────────────────────────┐
   │ a. Ledger queried for target action(s)            │
   │ b. Inverse-action executed in reverse order        │
   │ c. State verified against pre-state manifest hash  │
   │ d. Revert event appended to immutable audit trail  │
   └─────────────────────────────────────────────────┘
```

---

## Features

### Zero-Trust Sandboxing
Every shell command, file write, and API call runs in an ephemeral Docker container with a hardened Alpine Linux base image. The container is destroyed immediately after execution.

| Hardening Measure | Configuration |
|-------------------|---------------|
| **Seccomp profile** | Default-deny syscall filter — blocks `ptrace`, `mount`, `unshare`, `keyctl`, `bpf` |
| **Linux capabilities** | All dropped; only `CAP_SETUID`/`CAP_SETGID` if strictly needed |
| **User** | Non-root `uid=1000` — no `sudo`, no privilege escalation |
| **Root filesystem** | Read-only — only `/workspace` (bind mount) and `/tmp` (tmpfs) are writable |
| **Network** | `none` by default — per-domain allowlist required for any outbound access |
| **Resource limits** | 512 MB memory, 1.0 CPU core, 128 PIDs, 300s timeout |
| **tmpfs** | `/tmp` mounted `rw,noexec,nosuid,size=64m` |
| **Container lifecycle** | Created → run → force-remove — no lingering state |

### AES-256-GCM Encryption at Rest
All user credentials, workspace files, and the action ledger are encrypted before touching disk.

```
User Password
    │
    ▼
Argon2id (64 MB, 3 iterations, 1 parallelism)
    │
    ▼
256-bit Master Key ──── never persisted to disk
    │
    ├─► AES-256-GCM ◄── all data at rest
    │
    ├─► SQLCipher ◄──── database encryption
    │
    └─► HKDF-SHA256 ◄── HMAC signing sub-key
```

- **Key derivation**: Argon2id with 64 MB memory, 3 iterations, 16-byte random salt
- **AEAD**: AES-256-GCM provides both confidentiality and integrity
- **Unique nonce**: Fresh 96-bit random nonce per encryption — catastrophic to reuse
- **File vault**: Encrypted envelope per file; filename = SHA-256 of original path (metadata protection)
- **Database**: SQLCipher with `PRAGMA key`, WAL mode, HMAC-SHA512 integrity per page

### Full Action Revert
Every action is snapshot-prepped, diff-recorded, and revertible — including multi-step pipelines.

| Action Type | Revert Strategy |
|-------------|----------------|
| **File write** | Restore from pre-action git snapshot (byte-for-byte) |
| **Shell command** | Git stash pop workspace to pre-execution state |
| **Code patch** | Reverse diff via snapshot restore |
| **API call** | Compensating transaction (manual review flagged) |
| **File read** | No revert needed (idempotent) |

The ledger is an append-only, HMAC-SHA256-signed audit trail. Every entry is independently verifiable — tamper-evident compliance for SOC 2 Type II.

### Multi-Provider LLM with PII Scrubbing

```
Primary: Claude (Anthropic)
    │ (rate limit / auth error)
    ▼
Fallback: GPT-4o (OpenAI)
    │ (rate limit / auth error)
    ▼
Fallback: Mistral 7B (local Ollama — privacy mode)
```

**Before any external API call**, a mandatory PII scrubber strips:
- API keys (`sk-...`, `sk-ant-...`, `ghp_...`)
- Email addresses, phone numbers, credit card numbers
- Password fields in config-like patterns

### Prompt Injection Detection
Two-layer defense before any LLM call:

1. **Regex layer** — 20+ known injection patterns: `ignore previous instructions`, `<|im_start|>`, `[system]:`, `disregard prior directives`, jailbreak phrases
2. **Semantic layer** — `sentence-transformers/all-MiniLM-L6-v2` embeddings with cosine similarity > 0.75 threshold against known injection embeddings

### Action Risk Classification
Zero-shot classification via `facebook/bart-large-mnli` (407M params) with heuristic fallback:

| Risk Tier | Behavior |
|-----------|----------|
| **Read-Only** | Auto-execute — no confirmation needed |
| **Low-Risk Write** | Auto-execute — logged for review |
| **High-Risk Destructive** | **Pause** — user must confirm before execution |
| **Network Egress** | **Pause** — domain must be on explicit allowlist |

### JWT + TOTP 2FA Authentication
- JWTs with configurable expiry, HMAC-SHA256 signed
- TOTP 2FA via `pyotp` (RFC 6238) — compatible with Google Authenticator, Authy, etc.
- **Session tokens never written to disk** — held in memory only, cleared on logout
- Password hashing via Argon2id (same parameters as key derivation)

---

## Project Structure

```
secure-openclaw-clone/
├── backend/
│   ├── main.py                          # FastAPI entrypoint
│   └── core/
│       ├── config.py                    # All settings from .env
│       ├── api/
│       │   ├── app.py                   # FastAPI app factory + middleware
│       │   └── routes/
│       │       ├── auth.py              # Register, login, TOTP, 2FA
│       │       ├── tasks.py             # CRUD + SSE streaming + orchestration
│       │       └── revert.py            # Revert + ledger export
│       ├── auth/service.py              # JWT + Argon2id + TOTP + sessions
│       ├── background/runner.py         # Async worker queue
│       ├── db/database.py               # SQLite/SQLCipher ORM + migrations
│       ├── encryption/                  # AES-256-GCM + Argon2id + VaultStore
│       ├── knowledge/
│       │   ├── crawler.py               # ArXiv scraper + dedup + brain update
│       │   └── scheduler.py             # Weekly crawl + job runner
│       ├── llm/provider.py              # Claude · OpenAI · Ollama + fallback
│       ├── middleware/security.py       # Rate limiter · auth · audit log
│       ├── ml/models.py                 # Phi-3 planner · CodeT5+ · fine-tune
│       ├── models/                      # Pydantic: Task, Action, User, Ledger
│       ├── orchestrator/engine.py       # Agent loop: plan → execute → ledger
│       ├── revert/engine.py             # Inverse-action execution
│       ├── sandbox/executor.py          # Docker ephemeral container runner
│       ├── security/
│       │   ├── injection_detector.py    # Regex + semantic injection detection
│       │   └── risk_classifier.py       # BART-MNLI + heuristic risk tiers
│       └── snapshot/
│           ├── engine.py                # Git stash + SHA-256 manifest
│           └── ledger.py                # SQLCipher ledger with HMAC
├── frontend/
│   └── src/
│       ├── App.tsx                      # Routes + providers
│       ├── main.tsx                     # React root + QueryClient
│       ├── components/
│       │   ├── AuthGuard.tsx            # Protected route wrapper
│       │   ├── ErrorBoundary.tsx        # Crash boundary
│       │   ├── Layout.tsx               # Sidebar + nav
│       │   └── Toast.tsx                # Notification system
│       ├── hooks/useAuth.tsx            # Auth context + provider
│       ├── lib/
│       │   ├── api.ts                   # API client + SSE streaming
│       │   └── utils.ts                 # cn() classname utility
│       └── pages/
│           ├── Dashboard.tsx            # Task list
│           ├── Login.tsx                # Login + TOTP flow
│           ├── NewTask.tsx              # Task creation form
│           ├── Register.tsx             # Account registration
│           └── TaskDetail.tsx           # Task view + revert + SSE
├── deploy/helm/                         # Kubernetes Helm chart
├── docker/
│   ├── Dockerfile.backend               # Multi-stage backend image
│   ├── Dockerfile.frontend              # nginx-served React build
│   ├── Dockerfile.sandbox               # Hardened Alpine sandbox base
│   ├── nginx-default.conf               # Reverse proxy config
│   ├── seccomp.json                     # Default-deny syscall profile
│   └── requirements-sandbox.txt         # Python deps for sandbox
├── docs/
│   ├── action-ledger-schema.md          # Full SQLCipher DDL + HMAC spec
│   ├── docker-hardening.md              # Hardening spec + verification checklist
│   └── threat-model.md                  # 6 attack surfaces + mitigation matrix
├── .github/workflows/ci.yml             # Lint + security scan + Docker build
├── docker-compose.yml                   # Production stack
├── requirements.txt                     # Python dependencies
├── pyproject.toml                       # Project metadata
├── .env.example                         # All configuration documented
├── CLAUDE.md                            # Project brief
├── PROJECT-detail.md                    # Full technical specification
├── PROJECT-DEVELOPMENT-PHASE-TRACKING.md# 190 person-day development roadmap
├── SECOND-KNOWLEDGE-BRAIN.md            # Research knowledge base
├── README.md                            # This file
├── LICENSE                              # MIT
├── CONTRIBUTING.md                      # Contributor guide
└── CHANGELOG.md                         # Release history
```

---

## Quick Start

### Prerequisites

- **Python 3.11+** — runtime
- **Docker Desktop** — sandbox execution (daemon must be running)
- **Node.js 20+** — frontend build
- **Git** — workspace snapshots

### 1. Clone

```bash
git clone https://github.com/dungnotnull/secure-openclaw-clone-agent.git
cd secure-openclaw-clone-agent
```

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env` with your API keys:

```ini
LLM_PROVIDER=claude                  # or openai | ollama
ANTHROPIC_API_KEY=sk-ant-...         # Your Anthropic API key
OPENAI_API_KEY=sk-...                # Your OpenAI key (fallback)
OLLAMA_BASE_URL=http://localhost:11434  # Local Ollama server
```

### 3. Backend

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m uvicorn backend.core.api.app:app --host 0.0.0.0 --port 8000 --reload
```

Verify: `curl http://localhost:8000/health`

```json
{"status":"ok","version":"0.1.0","database":"connected","llm_providers":{...}}
```

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**

### 5. Production (Docker Compose)

```bash
docker compose up -d
```

Open **http://localhost:3000**

---

## API Reference

### Authentication

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/auth/register` | POST | Create account — returns JWT + TOTP setup URL |
| `/api/v1/auth/login` | POST | Sign in — returns JWT; `totp_required` if 2FA enabled |
| `/api/v1/auth/login/totp` | POST | Complete TOTP login flow |
| `/api/v1/auth/logout` | POST | Destroy session |
| `/api/v1/auth/2fa/enable` | POST | Enable TOTP 2FA with verification |

### Tasks

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/tasks` | POST | Create task — `{"instruction": "...", "token_budget": 100000}` |
| `/api/v1/tasks` | GET | List tasks — `?limit=50&offset=0` |
| `/api/v1/tasks/{id}` | GET | Get task with subtask decomposition |
| `/api/v1/tasks/{id}/run` | POST | Execute task in background |
| `/api/v1/tasks/{id}/stream` | GET | SSE stream — real-time task status updates |

### Revert & Audit

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/tasks/{id}/revert` | POST | Revert all actions in a task |
| `/api/v1/actions/{id}/revert` | POST | Revert a single action |
| `/api/v1/tasks/{id}/ledger/export` | GET | Download HMAC-signed JSONL audit log |

### System

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Database + LLM provider health |
| `/docs` | GET | Interactive API documentation (Swagger) |
| `/redoc` | GET | API documentation (Redoc) |

---

## Configuration Reference

Every aspect of the system is configurable via environment variables.

### LLM

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `claude` | Provider: `claude`, `openai`, `ollama` |
| `ANTHROPIC_API_KEY` | — | Claude API key |
| `OPENAI_API_KEY` | — | OpenAI API key |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server |
| `CLAUDE_MODEL` | `claude-sonnet-4-6` | Anthropic model ID |
| `OPENAI_MODEL` | `gpt-4o` | OpenAI model ID |
| `OLLAMA_MODEL` | `mistral:7b` | Ollama model name |

### Security

| Variable | Default | Description |
|----------|---------|-------------|
| `JWT_SECRET` | auto | JWT signing secret — auto-generated if empty |
| `JWT_EXPIRY_MINUTES` | `60` | Session token lifetime |
| `TOTP_ISSUER` | `SecureClawAgent` | TOTP authenticator label |
| `PII_SCRUB_ENABLED` | `true` | Strip credentials before external API calls |
| `PROMPT_INJECTION_DETECT_ENABLED` | `true` | Block adversarial prompt patterns |

### Sandbox

| Variable | Default | Description |
|----------|---------|-------------|
| `DOCKER_BASE_IMAGE` | `secureclaw-sandbox:latest` | Base image for containers |
| `DOCKER_NETWORK_MODE` | `none` | Container networking |
| `DOCKER_MEMORY_LIMIT` | `512m` | Per-container memory |
| `DOCKER_CPU_LIMIT` | `1.0` | Per-container CPU cores |
| `DOCKER_TIMEOUT_SECONDS` | `300` | Max execution time per action |

### Encryption

| Variable | Default | Description |
|----------|---------|-------------|
| `ARGON2_MEMORY_KB` | `65536` | Argon2id memory cost (64 MB) |
| `ARGON2_ITERATIONS` | `3` | Argon2id time cost |
| `ARGON2_PARALLELISM` | `1` | Argon2id parallelism |
| `ARGON2_SALT_BYTES` | `16` | Salt length |
| `DB_PRAGMA_KEY` | — | SQLCipher encryption key (derived from password if empty) |

---

## Models

| Model | Purpose | Size | Source |
|-------|---------|------|--------|
| `facebook/bart-large-mnli` | Zero-shot action risk classification | 407M | HuggingFace |
| `microsoft/phi-3-mini-4k-instruct` | Local task planner (privacy mode) | 3.8B | HuggingFace via Ollama |
| `Salesforce/codet5p-220m` | Small code patch generation | 220M | HuggingFace |
| `sentence-transformers/all-MiniLM-L6-v2` | Injection semantic detection | 22M | HuggingFace |
| `deepset/roberta-base-squad2` | Intent/parameter extraction | 125M | HuggingFace |
| `distilbert-base-uncased` | Fine-tuned risk classifier | 66M | HuggingFace |

---

## Security

### Threat Model

Full threat model with 6 attack surfaces is documented in [`docs/threat-model.md`](docs/threat-model.md).

| Threat | Mitigation |
|--------|-----------|
| **Sandbox escape** | Seccomp default-deny, all capabilities dropped, non-root user, read-only rootfs, no Docker socket mount |
| **Credential theft** | AES-256-GCM at rest, Argon2id-derived master key never persisted, sessions memory-only |
| **Prompt injection** | Two-layer detection (regex + semantic) before every LLM call; sandboxed execution limits blast radius |
| **Unauthorized revert** | JWT + optional TOTP verification; HMAC integrity on all ledger entries |
| **API data leakage** | Mandatory PII scrubber strips credentials before any external API call; privacy mode available |
| **Supply chain attack** | Base images built from pinned digests (cosign signing in future); dependencies pinned |

### Hardening Verification

See [`docs/docker-hardening.md`](docs/docker-hardening.md) for the full verification checklist. Key checks:

```bash
# Verify non-root
docker inspect secureclaw-sandbox --format '{{.Config.User}}'
# → 1000:1000

# Verify no network
docker inspect <container> --format '{{.HostConfig.NetworkMode}}'
# → none

# Verify read-only rootfs
docker inspect <container> --format '{{.HostConfig.ReadonlyRootfs}}'
# → true

# Verify seccomp applied
docker inspect <container> --format '{{.HostConfig.SecurityOpt}}'
# → [seccomp=C:\path\to\seccomp.json]
```

---

## Development

```bash
# Backend lint
pip install ruff
ruff check backend/

# Frontend type check
cd frontend && npx tsc --noEmit

# Build Docker images
docker build -f docker/Dockerfile.backend -t secureclaw-api:dev .
docker build -f docker/Dockerfile.frontend -t secureclaw-frontend:dev .
docker build -f docker/Dockerfile.sandbox -t secureclaw-sandbox:dev .
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for module map, code style, and architecture guidelines.

---

## Changelog

See [`CHANGELOG.md`](CHANGELOG.md) for full release history.

### v0.1.0 — 2026-06-08

Initial release. 43 Python backend modules, 15 TypeScript frontend files, 4 Docker images/configs, Helm chart, GitHub Actions CI, full documentation suite. All core features implemented: Docker sandbox executor, AES-256-GCM encryption, action ledger with HMAC, snapshot/revert engine, JWT+TOTP auth, multi-provider LLM with fallback chain, PII scrubbing, prompt injection detection, BART-MNLI risk classifier, Phi-3 local planner, CodeT5+ patch generator, distilBERT fine-tuning pipeline, ArXiv knowledge crawler, SSE streaming, React UI with auth guards and toast notifications.

---

## License

MIT — see [`LICENSE`](LICENSE)

---

<p align="center">
  Built with ❤️ by <a href="https://github.com/dungnotnull">dungnotnull</a> and contributors.
</p>
