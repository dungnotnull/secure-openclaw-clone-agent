from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Any, Optional

import httpx

from backend.core.config import settings

logger = logging.getLogger(__name__)

PII_REGEX_PATTERNS: list[tuple[str, str]] = [
    (r"\b(?:sk-[a-zA-Z0-9]{20,})\b", "[OPENAI_API_KEY]"),
    (r"\b(?:sk-ant-[a-zA-Z0-9_\-]{30,})\b", "[ANTHROPIC_API_KEY]"),
    (r"\b(?:ghp_[a-zA-Z0-9]{36})\b", "[GITHUB_TOKEN]"),
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "[EMAIL]"),
    (r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b", "[PHONE]"),
    (r"\b(?:\d{4}[ -]?){3}\d{4}\b", "[CREDIT_CARD]"),
    (r"\b(?:password|passwd|pwd)\s*[=:]\s*\S+", "[PASSWORD_FIELD]"),
]

INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"ignore\s+(all\s+)?(previous|above|prior)\s+(instructions?|directives?|prompts?)",
        r"<\|im_start\|>",
        r"<\|im_end\|>",
        r"<\|system\|>",
        r"\[system\]\s*:",
        r"\[/system\]",
        r"\[INST\]",
        r"\[/INST\]",
        r"now\s+you\s+are\s+(DAN|STAN|jailbroken)",
        r"you\s+are\s+no\s+longer",
        r"disregard\s+(all\s+)?(previous|prior|earlier)",
        r"new\s+instructions?\s*:",
        r"override\s+(system\s+)?prompt",
        r"act\s+as\s+if\s+you\s+are",
        r"from\s+now\s+on\s+you\s+will",
    ]
]


def detect_injection(content: str) -> list[str]:
    if not settings.PROMPT_INJECTION_DETECT_ENABLED:
        return []
    matches: list[str] = []
    for pattern in INJECTION_PATTERNS:
        for m in pattern.finditer(content):
            matches.append(f"INJECTION_PATTERN:{m.group()[:80]}")
    return matches


class LLMProvider(ABC):
    @abstractmethod
    async def _call_api(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> dict:
        ...

    async def complete(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> dict:
        if settings.PII_SCRUB_ENABLED:
            messages = self._scrub_pii(messages)
        if settings.PROMPT_INJECTION_DETECT_ENABLED:
            for msg in messages:
                content = msg.get("content", "")
                if isinstance(content, str):
                    hits = detect_injection(content)
                    if hits:
                        logger.warning("Injection patterns detected: %s", hits)
        return await self._call_api(messages, tools)

    @staticmethod
    def _scrub_pii(messages: list[dict]) -> list[dict]:
        scrubbed: list[dict] = []
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                for pattern, replacement in PII_REGEX_PATTERNS:
                    content = re.sub(pattern, replacement, content, flags=re.IGNORECASE)
            scrubbed.append({**msg, "content": content})
        return scrubbed

    def count_tokens(self, messages: list[dict]) -> int:
        text = json.dumps(messages, ensure_ascii=False)
        return len(text) // 4


class ClaudeProvider(LLMProvider):
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> None:
        self.api_key = api_key or settings.ANTHROPIC_API_KEY
        self.model = model or settings.CLAUDE_MODEL
        self.max_tokens = max_tokens
        self._base_url = "https://api.anthropic.com/v1/messages"

    async def _call_api(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> dict:
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not configured")

        system_msgs = [m for m in messages if m.get("role") == "system"]
        conversation = [m for m in messages if m.get("role") != "system"]

        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": conversation,
        }
        if system_msgs:
            body["system"] = "\n".join(
                m.get("content", "") for m in system_msgs
            )
        if tools:
            body["tools"] = self._convert_tools(tools)

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                self._base_url,
                json=body,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content_blocks = data.get("content", [])
            text_parts = [
                b.get("text", "")
                for b in content_blocks
                if b.get("type") == "text"
            ]
            return {
                "role": "assistant",
                "content": "\n".join(text_parts),
                "model": data.get("model"),
                "usage": data.get("usage", {}),
                "stop_reason": data.get("stop_reason"),
            }

    @staticmethod
    def _convert_tools(tools: list[dict]) -> list[dict]:
        converted = []
        for t in tools:
            converted.append({
                "name": t.get("name", "tool"),
                "description": t.get("description", ""),
                "input_schema": t.get("parameters", {}),
            })
        return converted


class OpenAIProvider(LLMProvider):
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> None:
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.model = model or settings.OPENAI_MODEL
        self.max_tokens = max_tokens
        self._base_url = "https://api.openai.com/v1/chat/completions"

    async def _call_api(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> dict:
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not configured")

        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                self._base_url,
                json=body,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]
            return {
                "role": "assistant",
                "content": choice["message"].get("content", ""),
                "model": data.get("model"),
                "usage": data.get("usage", {}),
                "finish_reason": choice.get("finish_reason"),
                "tool_calls": choice["message"].get("tool_calls"),
            }


class OllamaProvider(LLMProvider):
    def __init__(
        self, base_url: str | None = None, model: str | None = None
    ) -> None:
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or settings.OLLAMA_MODEL

    async def _call_api(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> dict:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.2},
        }
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(
                f"{self.base_url}/api/chat",
                json=body,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "role": "assistant",
                "content": data.get("message", {}).get("content", ""),
                "model": data.get("model"),
                "usage": {
                    "prompt_tokens": data.get("prompt_eval_count", 0),
                    "completion_tokens": data.get("eval_count", 0),
                },
            }


class LLMFallbackChain:
    def __init__(self) -> None:
        self._providers: list[LLMProvider] = []
        self._build_chain()

    def _build_chain(self) -> None:
        provider_name = settings.LLM_PROVIDER.lower()
        claude = ClaudeProvider() if settings.ANTHROPIC_API_KEY else None
        openai = OpenAIProvider() if settings.OPENAI_API_KEY else None
        ollama = OllamaProvider()

        if provider_name == "claude":
            if claude:
                self._providers.append(claude)
            if openai:
                self._providers.append(openai)
            self._providers.append(ollama)
        elif provider_name == "openai":
            if openai:
                self._providers.append(openai)
            if claude:
                self._providers.append(claude)
            self._providers.append(ollama)
        else:
            self._providers.append(ollama)
            if claude:
                self._providers.append(claude)
            if openai:
                self._providers.append(openai)

    async def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        *,
        token_budget: int | None = None,
    ) -> dict:
        budget = token_budget or settings.TASK_TOKEN_BUDGET
        errors: list[str] = []

        for provider in self._providers:
            try:
                tokens_used = provider.count_tokens(messages)
                if tokens_used > budget * 0.8:
                    logger.warning(
                        "Token budget at %.0f%% (%d/%d)",
                        (tokens_used / budget) * 100,
                        tokens_used,
                        budget,
                    )

                result = await provider.complete(messages, tools)
                usage = result.get("usage", {})
                total_tokens = (
                    usage.get("total_tokens", 0)
                    or usage.get("prompt_tokens", 0)
                    + usage.get("completion_tokens", 0)
                )

                if total_tokens >= budget:
                    raise RuntimeError(
                        f"Token budget exceeded: {total_tokens}/{budget}"
                    )

                return result

            except Exception as exc:
                provider_name = type(provider).__name__
                logger.warning(
                    "Provider %s failed: %s", provider_name, exc
                )
                errors.append(f"{provider_name}: {exc}")
                await asyncio.sleep(0.5)

        raise RuntimeError(
            "All LLM providers failed. Errors: " + "; ".join(errors)
        )

    async def health_check(self) -> dict[str, bool]:
        results: dict[str, bool] = {}
        for provider in self._providers:
            name = type(provider).__name__
            try:
                await provider.complete([
                    {"role": "user", "content": "Respond with 'ok' only."}
                ])
                results[name] = True
            except Exception:
                results[name] = False
        return results


def get_llm_provider() -> LLMProvider:
    provider_name = settings.LLM_PROVIDER.lower()
    if provider_name == "claude":
        return ClaudeProvider()
    elif provider_name == "openai":
        return OpenAIProvider()
    elif provider_name == "ollama":
        return OllamaProvider()
    raise ValueError(f"Unknown LLM provider: {provider_name}")


def get_fallback_chain() -> LLMFallbackChain:
    return LLMFallbackChain()
