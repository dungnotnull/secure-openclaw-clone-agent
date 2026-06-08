# Changelog

## [0.1.0] — 2026-06-08

### Added
- Zero-Trust Docker sandbox executor with seccomp profiles, capability dropping, non-root user, read-only rootfs, memory/CPU limits
- AES-256-GCM encryption layer with Argon2id key derivation (SecureStorage + VaultStore)
- Encrypted action ledger with SQLCipher + HMAC-SHA256 integrity verification
- Pre-action workspace snapshot engine via GitPython (git stash + SHA-256 manifest)
- Inverse-action revert engine supporting file restore, undo scripts, compensating API calls
- JWT authentication with configurable expiry and TOTP 2FA (pyotp)
- Multi-provider LLM backend: Anthropic Claude, OpenAI GPT-4o, local Ollama with automatic fallback chain
- PII scrubber: regex-based credential stripping before external LLM API calls
- Prompt injection detector: 20+ regex patterns + semantic embedding similarity via MiniLM-L6
- Action risk classifier: zero-shot via BART-MNLI with heuristic fallback + 4 risk tiers
- Task orchestrator: LLM-driven planning → subtask decomposition → sandbox dispatch → ledger recording
- Background task runner with async worker queue
- React 18 + TypeScript + Vite frontend with Dashboard, Task Creation, Task Detail, SSE streaming, Login with TOTP, Register
- AuthGuard, ErrorBoundary, Toast notification system, API client with token injection
- Knowledge crawler: weekly ArXiv scrape with keyword filtering, deduplication, auto-append to SECOND-KNOWLEDGE-BRAIN.md
- HMAC-SHA256 signed action ledger JSONL export with download endpoint
- Scheduler for background jobs (weekly crawl)
- docker-compose.yml production stack: FastAPI backend + nginx-served React frontend
- Dockerfiles: multi-stage backend, frontend (nginx), hardened sandbox (Alpine non-root)
- Helm chart for Kubernetes deployment
- GitHub Actions CI: lint, security scan (Bandit + Semgrep), Docker build
- Threat model document with 6 attack surfaces and mitigation matrices
- Docker hardening specification with verification checklist
- Encrypted action ledger SQL DDL with index tuning
- Local task planner: Phi-3-mini via Ollama integration
- Code patch generator: CodeT5+ 220M for small diffs
- Fine-tuning pipeline: distilBERT risk classifier with Trainer + sklearn metrics
- Rate limiter middleware, audit logger middleware, CORS hardening
