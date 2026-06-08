# Threat Model — SecureClawAgent

## Scope

This document identifies the attack surfaces, trust boundaries, and mitigation strategies for SecureClawAgent v0.1.0. The system consists of:
- **FastAPI backend** — handles auth, task orchestration, LLM calls, sandbox invocation
- **Docker sandbox runtime** — ephemeral containers that execute each action
- **React web UI** — browser-based user interface
- **Encrypted storage** — SQLCipher database, encrypted file vault
- **External LLM APIs** — Anthropic Claude, OpenAI GPT-4o, local Ollama

## Trust Boundaries

```
                          TRUST BOUNDARY A (network)
┌──────────────────────────────────────────────────────┐
│  Internet                                            │
│  ┌──────────────┐  ┌──────────────┐                  │
│  │ Claude API    │  │ OpenAI API   │                  │
│  └──────┬───────┘  └──────┬───────┘                  │
│         │                 │                           │
│  ┌──────▼─────────────────▼───────────────────────┐  │
│  │                API Gateway (FastAPI)             │  │
│  │  ┌──────────┐  ┌────────────┐  ┌────────────┐  │  │
│  │  │ JWT Auth  │  │ TOTP 2FA   │  │ Rate Limit  │  │  │
│  │  └──────────┘  └────────────┘  └────────────┘  │  │
│  └────────────────────┬─────────────────────────────┘  │
│                       │                                │
│              TRUST BOUNDARY B (process)                 │
│  ┌────────────────────▼─────────────────────────────┐  │
│  │              Task Orchestrator                     │  │
│  │  ┌─────────┐  ┌──────────┐  ┌────────────────┐   │  │
│  │  │ Planner  │  │ Tool Rtr  │  │ Result Agg     │   │  │
│  │  └─────────┘  └──────────┘  └────────────────┘   │  │
│  └────────────────────┬─────────────────────────────┘  │
│                       │                                │
│              TRUST BOUNDARY C (container)               │
│  ┌────────────────────▼─────────────────────────────┐  │
│  │     Docker Sandbox (ephemeral, per-action)         │  │
│  │     ┌──────────────────────────────────┐         │  │
│  │     │ seccomp | cap-drop | no-network  │         │  │
│  │     │ uid=1000 | ro-rootfs | tmpfs     │         │  │
│  │     └──────────────────────────────────┘         │  │
│  └──────────────────────────────────────────────────┘  │
│                       │                                │
│              TRUST BOUNDARY D (filesystem)              │
│  ┌────────────────────▼─────────────────────────────┐  │
│  │  Encrypted Storage                                │  │
│  │  ┌──────────────┐  ┌────────────────┐            │  │
│  │  │ SQLCipher DB  │  │ Encrypted Vault│            │  │
│  │  │ (AES-256-GCM) │  │ (file vault)   │            │  │
│  │  └──────────────┘  └────────────────┘            │  │
│  └──────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

## Attack Surfaces & Mitigations

### AS-1: Sandbox Escape
**Impact**: Critical — Attacker gains host OS code execution.
**Vector**: Malicious code inside a Docker container escapes to the host via kernel exploit, misconfigured mounts, or privileged container flags.

| Attack | Mitigation |
|--------|-----------|
| Kernel exploit via syscall | Seccomp profile blocks `ptrace`, `mount`, `unshare`, `keyctl`, `personality`, `bpf` |
| Privilege escalation inside container | Container runs as uid=1000 (non-root); `--privileged` never used |
| Docker socket exposure | Docker socket (`/var/run/docker.sock`) NOT mounted into container |
| Container breakout via shared mount | Root filesystem mounted `read_only=True`; `/tmp` is tmpfs with `noexec,nosuid` |
| User namespace escape | User namespace remapping configured on host Docker daemon |
| Capability abuse | All capabilities dropped; only `CAP_SETUID`, `CAP_SETGID` if strictly needed |

### AS-2: Credential Theft from Disk
**Impact**: Critical — API keys, user passwords, and session data exposed.
**Vector**: Attacker reads config files, SQLite databases, or log files containing plaintext credentials.

| Attack | Mitigation |
|--------|-----------|
| Plaintext API keys in .env | .env is git-ignored; runtime validates encryption is active before startup |
| SQLCipher DB without encryption | DB creation enforces `PRAGMA key` at open time; DB fails closed if no key |
| Session tokens on disk | Session tokens stored in memory only; never written to disk |
| Log files with secrets | Structured logging sanitizes credential patterns; debug mode requires explicit opt-in |
| Core dump containing keys | Resource limits (`RLIMIT_CORE=0`) prevent core dumps |

### AS-3: Prompt Injection
**Impact**: High — Agent executes unauthorized commands or exfiltrates data.
**Vector**: Adversarial text in user-supplied files causes the LLM planner to ignore safety instructions.

| Attack | Mitigation |
|--------|-----------|
| Direct injection in task instruction | Regex + semantic injection detector runs before planning |
| Indirect injection via file content | File contents scanned before entering LLM context window |
| System prompt override | System prompt uses XML-tagged structural separation; user content in `<user>` tags |
| Chain-of-thought hijacking | Output parser validates tool calls against allowed action types |

### AS-4: Unauthorized Revert
**Impact**: Medium — Attacker reverses a legitimate task, causing data loss.
**Vector**: Unauthenticated API call to `/tasks/{id}/revert` or `/actions/{id}/revert`.

| Attack | Mitigation |
|--------|-----------|
| Unauthenticated revert API call | All revert endpoints require valid JWT session |
| Replay of old revert request | HMAC-SHA256 integrity check on ledger entries |
| Revert to malicious previous state | Pre-state hash verified after revert; audit trail records revert event |
| Session hijacking | TOTP 2FA required for destructive operations (configurable) |

### AS-5: External API Data Leakage
**Impact**: High — User's source code or credentials sent to external LLM API.
**Vector**: The LLM provider's `complete()` call sends raw user content including secrets.

| Attack | Mitigation |
|--------|-----------|
| API keys in prompt | PII scrubber (regex + BERT NER) runs in `LLMProvider.complete()` before any external call |
| Source code leakage | Privacy mode (Ollama local) available for sensitive codebases |
| Man-in-the-middle on API call | All external API calls use HTTPS with certificate validation |
| Token logging by API provider | Task token budget limits total exposure per task |

### AS-6: Docker Image Supply Chain
**Impact**: High — Compromised base image contains backdoor.
**Vector**: Attacker publishes a malicious `python:3.11-alpine` image or dependency.

| Attack | Mitigation |
|--------|-----------|
| Malicious base image | Image pinned by digest (SHA256); `Dockerfile.sandbox` builds from verified source |
| Malicious pip package | `requirements-sandbox.txt` pins exact versions; no unpinned deps |
| Image tampering in transit | cosign signature verification before pull (Phase 3) |

## Risk Tolerance Matrix

| Risk Level | Acceptable? | Response |
|-----------|------------|----------|
| Sandbox escape (host root) | NO | Must be fully mitigated; critical blocker |
| Credential theft from disk | NO | Must be fully mitigated; critical blocker |
| Prompt injection (successful command exec) | NO | Mitigated via sandbox containment; injection may succeed but cannot escape |
| Prompt injection (non-destructive) | LOW tolerance | Detected + logged; user notified |
| External API data leakage | NO | PII scrubbing is mandatory and non-bypassable |
| Unauthorized revert | LOW tolerance | Requires session + optional TOTP |
| Docker image supply chain | LOW tolerance | Digest pinning + cosign in Phase 3 |

## Assets Requiring Protection

| Asset | Classification | Protection |
|-------|---------------|-----------|
| User password / master encryption key | Critical | Argon2id hashed; master key never persisted |
| API keys (Anthropic, OpenAI) | Critical | AES-256-GCM encrypted at rest; in-memory only at runtime |
| User source code / workspace files | High | Encrypted vault; sandboxed execution; privacy mode available |
| Action ledger | High | SQLCipher encrypted; HMAC-SHA256 integrity per entry |
| Session tokens | High | Memory-only; cleared on logout/timeout |
| Task history | Medium | Encrypted in SQLCipher DB |
| LLM API logs | Medium | Scrubbed of PII; retained per retention policy |
