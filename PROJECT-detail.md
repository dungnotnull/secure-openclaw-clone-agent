# PROJECT-detail.md — SecureClawAgent

## Executive Summary
SecureClawAgent is a security-hardened fork of the OpenClaw AI task agent runtime. It retains OpenClaw's core task-decomposition and tool-use loop while replacing the execution layer with a Zero-Trust sandboxed runtime, adding AES-256-GCM encryption for all user data at rest, and introducing a full action backup and revert system. Any task — from a single file write to a multi-step agentic pipeline — can be rolled back to its exact pre-execution state. The system is designed for developers, power users, and organizations that need the productivity of an autonomous AI agent without sacrificing data security or reversibility.

---

## Problem Statement
AI task agent runtimes (OpenClaw, OpenHands, SWE-agent, Aider) have reached practical utility but carry significant security and reliability risks:

- **No isolation**: Agents execute shell commands directly on the host OS with the user's own permissions. A hallucinated `rm -rf` or a prompt-injected command runs unguarded.
- **Plaintext user data**: API keys, file contents, and session history are stored in plaintext config files or SQLite databases without encryption.
- **No undo**: Once an agent deletes a file, rewrites a module, or calls an external API, there is no recovery path. Users must maintain their own backups.
- **Prompt injection risk**: Malicious content in files or web pages can hijack agent actions when the agent reads that content as context.

Research context: A 2024 USENIX Security study found that 78% of tested LLM agent frameworks were vulnerable to prompt injection attacks that caused unintended file system modifications. A 2023 survey of AI developer tools found that 0% offered cryptographic encryption of stored user credentials.

SecureClawAgent addresses all four risks without degrading the core agent capability.

---

## Target Users & Use Cases

| User Type | Primary Use Case |
|-----------|-----------------|
| Individual developers | Automated code refactoring, test generation, documentation — with confidence that the agent cannot permanently damage the codebase |
| Security-conscious teams | Internal tooling automation where user credentials and source code must remain encrypted |
| Enterprise IT admins | Automated system administration tasks in audited, sandboxed environments |
| AI researchers | Safe experimentation platform for testing new agent behaviors without risk of host system damage |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        SecureClawAgent System                        │
│                                                                      │
│  ┌──────────────┐    ┌────────────────────────────────────────────┐  │
│  │  Web UI       │    │              API Gateway (FastAPI)         │  │
│  │ React 18 /TS  │◄──►│  JWT Auth │ TOTP 2FA │ Rate Limiting      │  │
│  └──────────────┘    └────────────┬───────────────────────────────┘  │
│                                   │                                   │
│  ┌────────────────────────────────▼───────────────────────────────┐  │
│  │                      Task Orchestrator                          │  │
│  │   Task Parser → Subtask Decomposer → Tool Router → Result Agg  │  │
│  └────────────────────────────────┬───────────────────────────────┘  │
│                                   │                                   │
│  ┌────────────────────────────────▼───────────────────────────────┐  │
│  │                    LLM Provider Layer                           │  │
│  │   ┌─────────────┐  ┌─────────────┐  ┌──────────────────────┐  │  │
│  │   │ Claude API   │  │ OpenAI API  │  │  Local Ollama        │  │  │
│  │   │ (primary)    │  │ (fallback)  │  │  (privacy mode)      │  │  │
│  │   └─────────────┘  └─────────────┘  └──────────────────────┘  │  │
│  └────────────────────────────────┬───────────────────────────────┘  │
│                                   │                                   │
│  ┌─────────────────┐  ┌───────────▼───────────────────────────────┐  │
│  │ Backup & Revert │  │         Sandbox Execution Layer            │  │
│  │ Engine          │◄─┤   Pre-snapshot → Docker Container → Diff  │  │
│  │ ┌─────────────┐ │  │   ┌─────────────────────────────────────┐ │  │
│  │ │ Action Ledger│ │  │   │ Hardened Container (Alpine Linux)   │ │  │
│  │ │ (SQLCipher)  │ │  │   │ No network | Capability drop        │ │  │
│  │ └─────────────┘ │  │   │ Read-only OS layer | tmpfs workspace │ │  │
│  │ ┌─────────────┐ │  │   └─────────────────────────────────────┘ │  │
│  │ │ Git Snapshot │ │  └───────────────────────────────────────────┘  │
│  │ └─────────────┘ │                                                  │
│  └─────────────────┘                                                  │
│                                                                       │
│  ┌────────────────────────────────────────────────────────────────┐   │
│  │                  Encrypted Storage Layer                        │   │
│  │  SQLCipher DB (AES-256-GCM) │ Encrypted File Vault │ Key Store │   │
│  │  Argon2id key derivation from user password                     │   │
│  └────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Component | Technology | Source |
|-----------|-----------|--------|
| Backend framework | FastAPI 0.111+ | PyPI |
| Task orchestration | Custom fork of OpenClaw planner | GitHub (OpenClaw) |
| LLM abstraction | LiteLLM 1.40+ | PyPI |
| Sandbox execution | Docker SDK for Python 7.0+ | PyPI |
| Hardened base image | `python:3.11-alpine` (custom hardened) | Docker Hub |
| Encrypted database | SQLCipher via `sqlcipher3` Python binding | PyPI |
| Key derivation | `argon2-cffi` 23.1+ | PyPI |
| Symmetric encryption | `cryptography` (AES-256-GCM) | PyPI |
| 2FA / TOTP | `pyotp` 2.9+ | PyPI |
| Session auth | `python-jose` JWT | PyPI |
| Git snapshots | `GitPython` 3.1+ | PyPI |
| Frontend framework | React 18 + TypeScript 5 | npm |
| UI component library | shadcn/ui + Tailwind CSS | npm |
| Static analysis | Bandit, Semgrep | PyPI |
| Task intent classifier | `facebook/bart-large-mnli` (HuggingFace) | HuggingFace |
| Local LLM planner | `microsoft/phi-3-mini-4k-instruct` | HuggingFace |

---

## ML/DL Models Section

### Action Risk Classifier
- **Model**: `facebook/bart-large-mnli` — zero-shot classification
- **Purpose**: Before each tool call, classify the action into a risk tier (Read-Only / Low-Risk Write / High-Risk Destructive / Network Egress). High-Risk and Network Egress tiers require explicit user confirmation.
- **Inference**: Local, CPU-only, < 200ms per classification
- **Fine-tuning plan**: Phase 2 — collect labeled action logs from beta users to fine-tune a smaller distilBERT classifier for < 20ms latency

### Local Task Planner (Privacy Mode)
- **Model**: `microsoft/phi-3-mini-4k-instruct` (3.8B parameters, 4-bit GGUF)
- **Purpose**: Full task decomposition and tool routing without external API calls
- **Inference**: Ollama backend; 4–8 GB VRAM or CPU fallback
- **Training data**: None initially; uses base instruction-following capability

### Code Patch Generator
- **Model**: `Salesforce/codet5p-220m`
- **Purpose**: Generate small code patches inside the sandbox for refactoring tasks; reduces LLM API token usage for trivial edits
- **Fine-tuning plan**: Phase 3 — fine-tune on user-approved patch history (opt-in)

### Intent Clarification QA
- **Model**: `deepset/roberta-base-squad2`
- **Purpose**: Extract structured action parameters from ambiguous user instructions before sending to the LLM planner

---

## External LLM API Integration

SecureClawAgent uses a `LLMProvider` abstraction defined in `core/llm/provider.py`. All providers implement the same `complete(messages, tools)` interface. The active provider is selected via `LLM_PROVIDER` environment variable.

```python
# Pluggable backend selection (pseudocode)
LLM_PROVIDER = "claude"   # or "openai" | "ollama"
ANTHROPIC_API_KEY = "..."
OPENAI_API_KEY = "..."
OLLAMA_BASE_URL = "http://localhost:11434"
```

**PII scrubbing**: Before any user file content or environment variable is sent to an external API, a regex + NER pass strips API keys, email addresses, phone numbers, and passwords. This is non-bypassable — it runs inside the `LLMProvider` base class `complete()` method.

**Graceful fallback chain**: Claude API → OpenAI API → Local Ollama. If the primary provider returns a rate-limit or auth error, the system automatically retries on the next available provider and logs the fallback event.

---

## Feature Specification

### MVP Features (Phase 1)
- [ ] Task input via web UI and CLI
- [ ] Task decomposition into ordered subtasks using LLM planner
- [ ] Sandboxed shell command execution (Docker container per command)
- [ ] File read/write tools operating inside the sandbox workspace
- [ ] Pre-action snapshot (git stash of workspace)
- [ ] Post-action diff recording in encrypted action ledger
- [ ] Single-task revert via action ledger lookup
- [ ] AES-256-GCM encryption of all stored user data
- [ ] JWT + TOTP 2FA authentication
- [ ] Web UI: task input, progress stream, revert button per action

### Advanced Features (Phase 3+)
- [ ] Multi-step pipeline revert (roll back N actions atomically)
- [ ] Per-domain network allowlist for sandbox containers
- [ ] Prompt injection detector (regex + semantic similarity to known injection patterns)
- [ ] Action risk tier display with per-tier confirmation gates
- [ ] Action replay: re-run a previously successful task from ledger
- [ ] Shared team workspace with per-user encrypted key isolation
- [ ] Webhook notifications on task completion or revert
- [ ] Action ledger export (signed JSON, HMAC-verified)
- [ ] Self-hosted container registry for custom sandbox base images
- [ ] Plugin system for custom tools (same sandbox isolation guarantee)

---

## Full End-to-End Data Flow

1. **User submits task** via web UI or CLI; JWT token validated at API gateway
2. **Task Parser** normalizes the instruction and checks for prompt injection patterns
3. **Action Risk Classifier** (BART-MNLI) assigns a risk tier to the overall task
4. **LLM Planner** decomposes the task into an ordered list of subtasks with tool assignments
5. For each subtask:
   a. **Snapshot Engine** records pre-state: git stash + file manifest hash stored in action ledger
   b. **Docker Executor** spawns an ephemeral hardened container, mounts the workspace volume read-write
   c. The tool (shell command, file write, web fetch) executes inside the container
   d. Container exits; **Diff Recorder** computes workspace diff and stores it in the encrypted action ledger with an inverse-action descriptor
   e. If the action was High-Risk, the web UI pauses and waits for user confirmation before proceeding
6. **Result Aggregator** collects outputs from all subtasks, generates a summary via the LLM
7. **Web UI** displays result, elapsed time, and a timeline of all actions with revert buttons
8. If the user requests **Revert**:
   a. Ledger is queried for the target action(s)
   b. Inverse-action descriptors are executed in reverse order (file restore from snapshot, undo script, compensating API call)
   c. Revert result is verified against the pre-state manifest hash
   d. Revert event is written to the ledger (immutable audit trail)

---

## Privacy & Security

### Encryption Architecture
- All user data at rest encrypted with AES-256-GCM
- Master encryption key derived via Argon2id from user password (salt stored, key never stored)
- Database uses SQLCipher; file vault uses per-file encrypted envelopes
- Session tokens held in memory only; cleared on logout or timeout

### Sandbox Hardening
- Docker containers run as non-root user (`uid=1000`)
- Linux capabilities dropped to minimal set: `CAP_NET_BIND_SERVICE` only if network allowlisted
- `seccomp` profile blocks dangerous syscalls: `ptrace`, `mount`, `unshare`, `keyctl`
- Container filesystem: read-only OS layer + tmpfs for `/tmp` + workspace bind mount
- Container memory limit: 512 MB default; CPU limit: 1.0 core

### Threat Model
| Threat | Mitigation |
|--------|-----------|
| Prompt injection via file content | Injection detector + sandboxed execution (injected commands cannot escape container) |
| Credential theft from disk | AES-256-GCM encryption; master key never written to disk |
| Sandbox escape | Seccomp + capability drop; no privileged mode; Docker daemon socket not mounted |
| Replay attacks on action ledger | HMAC-SHA256 integrity verification per ledger entry |
| Unauthorized revert | Revert requires authenticated session + optional TOTP confirmation for destructive operations |

### Compliance Notes
- Action ledger provides immutable audit trail suitable for SOC 2 Type II evidence
- GDPR: all user data deletion cascade-clears encrypted ledger entries; key deletion renders data unrecoverable

---

## Key Python Dependencies

```
fastapi==0.111.0
uvicorn[standard]==0.30.0
docker==7.0.0
sqlcipher3==0.5.3
argon2-cffi==23.1.0
cryptography==42.0.5
python-jose[cryptography]==3.3.0
pyotp==2.9.0
gitpython==3.1.43
litellm==1.40.0
anthropic==0.28.0
openai==1.30.0
transformers==4.41.0
torch==2.3.0
httpx==0.27.0
pydantic==2.7.0
bandit==1.7.8
semgrep==1.75.0
```

---

## Improvement Suggestions (Beyond Original Idea)

1. **Prompt injection firewall**: A dedicated ML model trained on known injection patterns runs before every LLM call, blocking adversarial content in user-supplied files before it reaches the planner.
2. **Signed action ledger exports**: Allow teams to export the action ledger as a cryptographically signed JSON artifact (HMAC-SHA256) for compliance audits.
3. **Capability negotiation UI**: Before starting a task, show the user exactly which capabilities (network, file system paths, external APIs) the agent will need — get explicit approval before spawning any container.
4. **Diff preview before execution**: For file-write actions, show a rendered diff in the web UI and require user confirmation before applying — similar to a "dry run" mode.
5. **Action replay with parameter substitution**: Re-run a successful historical task from the ledger but with modified parameters, without re-running the planning step.
6. **Federated key management**: Integrate with HashiCorp Vault or AWS KMS as an alternative to password-derived keys for enterprise deployments.
7. **Container image signing**: All sandbox base images are signed with cosign; the executor verifies the signature before pulling, preventing supply-chain attacks via compromised base images.
8. **Time-boxed task budgets**: Each task has a maximum elapsed time and token budget; exceeding either pauses execution and notifies the user rather than silently continuing.
