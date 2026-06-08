# CLAUDE.md — secure-openclaw-clone

## Project Identity
- **Name**: SecureClawAgent
- **Tagline**: A security-hardened AI task agent runtime with Zero-Trust sandboxing and full action revert capability
- **Status**: Phase 0 — Research & Architecture Design
- **Based On**: OpenClaw open-source AI task agent runtime

## Core Problem
Standard AI task agent runtimes (OpenClaw, OpenHands, OpenDevin) execute arbitrary code and system commands on behalf of users with minimal security guarantees. User data is stored in plaintext, actions execute with broad OS permissions, and there is no mechanism to undo completed actions. SecureClawAgent closes all three gaps: every action is pre-snapshotted and runs inside an ephemeral Docker container with a minimal capability grant, all user credentials and session context are AES-256-GCM encrypted at rest, and a time-travel revert system allows any completed task — including multi-step pipelines — to be fully rolled back on request.

## Architecture Summary
- **Platform**: Python 3.11+ backend (FastAPI), React 18 / TypeScript frontend
- **Sandboxing**: Docker SDK — ephemeral container per action, minimal Linux capability set, no external network by default
- **Encryption**: AES-256-GCM for all user data at rest; SQLCipher-backed action ledger; Argon2id key derivation
- **LLM Backend**: Pluggable via `LLMProvider` interface — Claude API, GPT-4o, or local Ollama; config key `LLM_PROVIDER`
- **Backup Engine**: Git-backed workspace snapshots + encrypted SQLite action ledger; inverse-action revert semantics
- **Auth**: JWT + TOTP 2FA; session tokens stored only in memory, never written to disk unencrypted

## Key Technical Decisions
1. Fork OpenClaw's task-planning and tool-use loop; replace the execution layer entirely with a sandboxed Docker executor
2. Every tool call spawns a fresh ephemeral container from a hardened base image; container is destroyed after the call
3. Before each action, capture a workspace snapshot (git stash + file manifest hash); after action, record diff and inverse-action descriptor in the encrypted ledger
4. AES-256-GCM master key derived from user password via Argon2id (memory: 64 MB, iterations: 3); master key is never persisted — only a salt is stored
5. Zero-Trust network policy: sandbox containers get no internet access by default; user must explicitly grant a per-domain allowlist per task
6. Revert system uses inverse-action semantics: file writes → restore from snapshot, shell commands → run undo script, API calls → execute compensating transaction
7. All LLM prompts containing user data are stripped of PII before leaving the local machine when using external API providers

## External LLM API Integrations

| Provider | Config Key | Default Model | Notes |
|----------|-----------|---------------|-------|
| Claude (Anthropic) | `ANTHROPIC_API_KEY` | claude-sonnet-4-6 | Primary provider |
| OpenAI GPT-4o | `OPENAI_API_KEY` | gpt-4o | Fallback provider |
| Local Ollama | `OLLAMA_BASE_URL` | mistral:7b | Privacy/offline mode; no external calls |

## HuggingFace Models in Use

| Model ID | Purpose | Link |
|----------|---------|------|
| `microsoft/phi-3-mini-4k-instruct` | Lightweight local task planner (low-resource mode) | [HF](https://huggingface.co/microsoft/phi-3-mini-4k-instruct) |
| `Salesforce/codet5p-220m` | Code generation and patch generation in sandbox | [HF](https://huggingface.co/Salesforce/codet5p-220m) |
| `deepset/roberta-base-squad2` | Action intent classification and risk scoring | [HF](https://huggingface.co/deepset/roberta-base-squad2) |
| `facebook/bart-large-mnli` | Zero-shot action category classification | [HF](https://huggingface.co/facebook/bart-large-mnli) |

## Active Development Tasks
- [ ] Audit OpenClaw source for security vulnerabilities and attack surface
- [ ] Design encrypted SQLite action ledger schema (SQLCipher)
- [ ] Implement Docker SDK sandbox executor with capability drop
- [ ] Implement AES-256-GCM encryption layer and Argon2id key derivation
- [ ] Build action snapshot system (git stash + file manifest)
- [ ] Build inverse-action revert engine
- [ ] Integrate pluggable LLM backend (`LLMProvider` abstraction)
- [ ] Build React web UI with task history timeline and one-click revert
- [ ] Write integration test suite for sandbox escape and privilege escalation scenarios
- [ ] Security audit: static analysis (Bandit, Semgrep) + dynamic fuzzing

## Related Files
- `PROJECT-detail.md` — Full technical specification and architecture
- `PROJECT-DEVELOPMENT-PHASE-TRACKING.md` — Phase-by-phase development roadmap
- `SECOND-KNOWLEDGE-BRAIN.md` — Research knowledge base (auto-updated)
