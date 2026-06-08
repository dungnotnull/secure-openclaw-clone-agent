from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- LLM ----
    LLM_PROVIDER: Literal["claude", "openai", "ollama"] = "claude"
    ANTHROPIC_API_KEY: str | None = None
    OPENAI_API_KEY: str | None = None
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    CLAUDE_MODEL: str = "claude-sonnet-4-6"
    OPENAI_MODEL: str = "gpt-4o"
    OLLAMA_MODEL: str = "mistral:7b"

    # ---- Encryption ----
    SECURE_VAULT_DIR: Path = PROJECT_ROOT / "data" / "vault"
    ARGON2_MEMORY_KB: int = 65536
    ARGON2_ITERATIONS: int = 3
    ARGON2_PARALLELISM: int = 1
    ARGON2_SALT_BYTES: int = 16

    # ---- Database ----
    DB_PATH: Path = PROJECT_ROOT / "data" / "secureclaw.db"
    DB_PRAGMA_KEY: str | None = None

    # ---- Auth ----
    JWT_SECRET: str = Field(default_factory=lambda: secrets.token_hex(32))
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_MINUTES: int = 60
    TOTP_ISSUER: str = "SecureClawAgent"

    # ---- Sandbox ----
    DOCKER_BASE_IMAGE: str = "secureclaw-sandbox:latest"
    DOCKER_NETWORK_MODE: str = "none"
    DOCKER_MEMORY_LIMIT: str = "512m"
    DOCKER_CPU_LIMIT: float = 1.0
    DOCKER_TIMEOUT_SECONDS: int = 300
    SANDBOX_SECCOMP_PROFILE: Path = PROJECT_ROOT / "docker" / "seccomp.json"

    # ---- Workspace ----
    WORKSPACE_DIR: Path = PROJECT_ROOT / "data" / "workspace"

    # ---- Limits ----
    TASK_TOKEN_BUDGET: int = 100_000
    ACTION_MAX_RETRIES: int = 3
    REVERT_AUDIT_ENABLED: bool = True

    # ---- Security ----
    PII_SCRUB_ENABLED: bool = True
    PROMPT_INJECTION_DETECT_ENABLED: bool = True


settings = Settings()
