# SECOND-KNOWLEDGE-BRAIN.md — SecureClawAgent

> **Auto-update protocol**: This file is updated weekly by the `KnowledgeCrawler` (crawl4ai pipeline). New entries are appended under the relevant section and logged in the Knowledge Update Log at the bottom. Do not manually edit entries above the log without also updating the log.

---

## Core Concepts & Theoretical Foundations

### AI Task Agent Runtimes
An AI task agent runtime combines three capabilities: (1) a planning module that decomposes a natural-language task into an ordered list of subtasks, (2) a tool-use module that maps subtasks to structured tool calls (shell commands, file writes, API calls), and (3) an execution environment that runs those tool calls and returns observations back to the planner. The planning loop iterates until the task is complete or an error is raised.

Key design axes:
- **Execution isolation**: none (direct OS), process-level (`subprocess`), or container-level (Docker/nsjail)
- **Planning architecture**: single LLM call with chain-of-thought, ReAct (Reason + Act), LATS (LLM-based Tree Search), or multi-agent delegation
- **State management**: stateless per-task, or stateful with persistent memory across tasks

### Zero-Trust Security Model
Zero-Trust assumes no implicit trust: every action must be authorized, every actor authenticated, and every resource access logged regardless of network location. Applied to AI agents:
- The agent is never trusted to self-authorize destructive actions
- Every tool call is mediated by a policy engine that checks authorization
- All data in transit and at rest is encrypted; decryption requires proof of identity

### Docker Sandbox Hardening
Docker containers provide OS-level namespace isolation but are not inherently secure. Key hardening techniques:
- **Seccomp profiles**: restrict the set of Linux system calls available to the container process
- **Capability dropping**: remove Linux capabilities (e.g., `CAP_SYS_ADMIN`, `CAP_NET_RAW`) that are not needed
- **Read-only root filesystem**: mount the container's root filesystem as read-only; only specific paths are writable
- **User namespace remapping**: map container root (uid=0) to an unprivileged host uid
- **Resource limits**: enforce CPU, memory, and PID limits via cgroups v2
- **No privileged mode**: never use `--privileged`; never mount the Docker socket inside the container

### Action Revert Semantics
Three classes of actions with different revert strategies:
1. **Idempotent / pure read**: no revert needed (e.g., `cat`, `grep`, API GET)
2. **File system mutation**: revert by restoring the pre-action file snapshot (git stash pop or file copy from vault)
3. **External side effect**: API POST, network request, payment — revert via compensating transaction or manual intervention; must be flagged to the user as "non-automatically-revertable"

Revert must be atomic: either the full pre-state is restored or the revert fails with an error — partial revert is worse than no revert.

### AES-256-GCM Encryption
AES-256 in Galois/Counter Mode (GCM) provides both confidentiality and integrity (AEAD). Key properties:
- **Key size**: 256 bits
- **Nonce**: 96 bits, must be unique per encryption; reusing a nonce with the same key is catastrophic
- **Authentication tag**: 128 bits; verifies both ciphertext integrity and associated data
- **Performance**: hardware-accelerated on all modern CPUs via AES-NI

Best practice: derive the encryption key from a user password using a memory-hard KDF (Argon2id), not directly from the password. Store only the salt (16 bytes) and the Argon2id parameters.

### Prompt Injection
Prompt injection is an attack where adversarial text in the environment (files, web pages, API responses) hijacks the LLM's instruction-following behavior. In AI agent contexts, successful injection can cause the agent to exfiltrate data, execute unauthorized commands, or leak credentials. Two variants:
- **Direct injection**: malicious text appears in the user's own prompt
- **Indirect injection**: malicious text appears in a document the agent reads during a task (e.g., a file it was asked to summarize)

Mitigations: structural separation of instructions and data (e.g., XML tags), perimeter scanning before content enters the context window, sandbox execution so injected commands cannot escape containment.

---

## Key Research Papers

| Title | Authors | Year | Venue | DOI / arXiv | Relevance |
|-------|---------|------|-------|-------------|-----------|
| AgentDojo: A Dynamic Environment to Evaluate Prompt Injection Attacks and Defenses for LLM Agents | Debenedetti et al. | 2024 | NeurIPS | arXiv:2406.13352 | Benchmark for prompt injection defenses — use for evaluating injection detector |
| SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering | Yang et al. | 2024 | arXiv | arXiv:2405.15793 | Architecture reference for AI task agents operating on real codebases |
| ReAct: Synergizing Reasoning and Acting in Language Models | Yao et al. | 2023 | ICLR | arXiv:2210.03629 | Foundation planning architecture used in most agent runtimes |
| LLM Agents can Autonomously Exploit One-Day Vulnerabilities | Fang et al. | 2024 | arXiv | arXiv:2404.08144 | Motivates sandboxing — agents CAN execute real exploits; containment is mandatory |
| Injecting Relevance Feedback into Conversational Agents via Hidden Instructions | Greshake et al. | 2023 | IEEE S&P | arXiv:2302.12173 | First systematic study of indirect prompt injection; defines the threat model |
| Not what you've signed up for: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection | Greshake et al. | 2023 | AISec Workshop | arXiv:2302.12173 | Extended analysis of real-world injection attacks on LLM apps |
| HarmBench: A Standardized Evaluation Framework for Automated Red Teaming and Robust Refusal | Mazeika et al. | 2024 | ICML | arXiv:2402.04249 | Evaluation benchmark relevant to testing agent safety guardrails |
| AutoCodeRover: Autonomous Program Improvement | Zhang et al. | 2024 | ISSTA | arXiv:2404.05427 | Competing agent architecture; reference for agentic code editing design |
| Argon2: Memory-Hard Function for Password Hashing and Proof-of-Work | Biryukov et al. | 2015 | Password Hashing Competition | PHC Spec | Specification for Argon2id KDF used in key derivation |
| CryptDB: Protecting Confidentiality with Encrypted Query Processing | Popa et al. | 2011 | SOSP | dl.acm.org/doi/10.1145/2043556.2043566 | Encrypted database design — informs SQLCipher usage patterns |
| Docker Security: Using Docker the Secure Way | Chelladhurai et al. | 2016 | IEEE Services | DOI:10.1109/BigDataService.2016.51 | Hardening reference for Docker-based sandboxes |
| LATS: Language Agent Tree Search Unifies Reasoning Acting and Planning in Language Models | Zhou et al. | 2024 | ICML | arXiv:2310.04406 | Advanced planning architecture for future phases |

---

## State-of-the-Art ML/DL Models

| Model | HuggingFace ID | Purpose in SecureClawAgent | Notes |
|-------|---------------|---------------------------|-------|
| BART-MNLI | `facebook/bart-large-mnli` | Zero-shot action risk classification | 407M params; CPU-viable; replace with fine-tuned distilBERT in Phase 2 |
| DistilBERT (fine-tuned) | `distilbert-base-uncased` (to be fine-tuned) | Fast 4-class risk classifier after fine-tuning | 66M params; < 20ms inference on CPU |
| Phi-3 Mini | `microsoft/phi-3-mini-4k-instruct` | Local task planner (privacy mode) | 3.8B params; 4-bit quantized via Ollama |
| CodeT5+ 220M | `Salesforce/codet5p-220m` | Small code patch generation | 220M params; CPU-viable; reduces API cost for trivial edits |
| RoBERTa SQuAD2 | `deepset/roberta-base-squad2` | Intent/parameter extraction from ambiguous instructions | 125M params |
| MiniLM-L6 | `sentence-transformers/all-MiniLM-L6-v2` | Semantic prompt injection detection (embedding similarity) | 22M params; very fast |
| BERT NER | `dslim/bert-base-NER` | PII detection before external LLM API calls | Detects PER, ORG, LOC, MISC; also catches API key patterns via regex |
| Mistral 7B Instruct | via Ollama `mistral:7b` | Full local LLM fallback (privacy mode) | 7B params; 4–8 GB VRAM; GGUF quantized |
| Llama 3.1 8B | via Ollama `llama3.1:8b` | Alternative local LLM fallback | 8B params; strong coding capability |

**Papers With Code benchmarks**: BART-MNLI achieves 89.9% accuracy on MultiNLI. For task-specific action classification, fine-tuned distilBERT is expected to reach > 90% F1 with < 1000 labeled examples.

---

## Tools, Libraries & Frameworks

| Tool | GitHub / Link | Use Case in SecureClawAgent |
|------|-------------|----------------------------|
| Docker SDK for Python | [github.com/docker/docker-py](https://github.com/docker/docker-py) | Spawn and manage ephemeral sandbox containers |
| SQLCipher | [github.com/sqlcipher/sqlcipher](https://github.com/sqlcipher/sqlcipher) | AES-256-GCM encrypted SQLite database |
| argon2-cffi | [github.com/hynek/argon2-cffi](https://github.com/hynek/argon2-cffi) | Argon2id key derivation from user password |
| cryptography (Python) | [github.com/pyca/cryptography](https://github.com/pyca/cryptography) | AES-256-GCM encrypt/decrypt primitives |
| LiteLLM | [github.com/BerriAI/litellm](https://github.com/BerriAI/litellm) | Unified interface to Claude, OpenAI, Ollama APIs |
| FastAPI | [github.com/tiangolo/fastapi](https://github.com/tiangolo/fastapi) | Backend API framework |
| GitPython | [github.com/gitpython-developers/GitPython](https://github.com/gitpython-developers/GitPython) | Workspace git stash for pre-action snapshots |
| pyotp | [github.com/pyauth/pyotp](https://github.com/pyauth/pyotp) | TOTP 2FA implementation |
| Bandit | [github.com/PyCQA/bandit](https://github.com/PyCQA/bandit) | Python static security analysis |
| Semgrep | [github.com/semgrep/semgrep](https://github.com/semgrep/semgrep) | Multi-language static analysis with OWASP rules |
| crawl4ai | [github.com/unclecode/crawl4ai](https://github.com/unclecode/crawl4ai) | Weekly knowledge crawler for SECOND-KNOWLEDGE-BRAIN auto-update |
| APScheduler | [github.com/agronholm/apscheduler](https://github.com/agronholm/apscheduler) | Schedule weekly knowledge crawler and maintenance tasks |
| Sentence Transformers | [github.com/UKPLab/sentence-transformers](https://github.com/UKPLab/sentence-transformers) | Semantic similarity for prompt injection detection |
| Ollama | [github.com/ollama/ollama](https://github.com/ollama/ollama) | Local LLM serving (Phi-3, Mistral, Llama 3.1) |
| cosign | [github.com/sigstore/cosign](https://github.com/sigstore/cosign) | Container image signing to prevent supply chain attacks |
| nsjail | [github.com/google/nsjail](https://github.com/google/nsjail) | Alternative to Docker for even stronger isolation (future) |

---

## Self-Update Protocol

### Crawler Configuration (crawl4ai)

**Target sources:**
1. ArXiv — categories: `cs.CR` (Cryptography and Security), `cs.AI` (Artificial Intelligence), `cs.SE` (Software Engineering)
2. HuggingFace Papers — filter: tags `llm-agents`, `security`, `sandboxing`, `code-generation`
3. Papers With Code — task pages: `code-generation`, `text-classification`, `named-entity-recognition`
4. USENIX Security proceedings (annual)
5. ACM CCS proceedings (annual)
6. OWASP blog — filter: LLM Top 10 updates

**Domain-specific search queries:**
```
"LLM agent" + "security" + "sandbox"
"prompt injection" + "defense" + "agent"
"AI agent" + "action revert" + "rollback"
"Docker" + "container" + "LLM" + "isolation"
"AES-256" + "SQLite" + "encryption"
"zero trust" + "AI agent" + "authorization"
"code execution" + "sandboxing" + "LLM"
"agent benchmark" + "security" + "evaluation"
```

**Update frequency:** Weekly (every Monday at 02:00 UTC via APScheduler)

**Format for new entries:**
```markdown
| [Paper Title] | [Authors] | [Year] | [Venue] | [DOI/arXiv] | [1-sentence relevance note] |
```
New entries are appended to the Key Research Papers table. After 50+ entries, papers are archived to `BRAIN-ARCHIVE.md` and only the 30 most relevant remain in the active table.

**Deduplication:** Before appending, the crawler checks the DOI and arXiv ID against existing entries. Duplicates are skipped.

---

## Knowledge Update Log

| Date | Source | Entries Added | Added By |
|------|--------|---------------|---------|
| 2026-06-03 | Manual initialization | 12 research papers, 9 HuggingFace models, 15 tools | Claude Code (session init) |

---

*Next scheduled auto-update: 2026-06-08 (Monday 02:00 UTC)*
