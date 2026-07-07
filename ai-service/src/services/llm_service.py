"""Groq client wrapper with circuit breaker and rule-based fallback."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

try:  # pragma: no cover - optional runtime dependency
    from groq import Groq
except Exception:  # pragma: no cover - keep isolated tests working without heavy deps
    Groq = None

from ..config.constants import GROQ_CIRCUIT_RESET_SECONDS, GROQ_FAILURE_THRESHOLD
from ..config.settings import settings


@dataclass(slots=True)
class LLMResult:
    text: str
    generated_via: str
    fallback_reason: str | None = None


class CircuitBreaker:
    def __init__(self, failure_threshold: int = GROQ_FAILURE_THRESHOLD, reset_seconds: int = GROQ_CIRCUIT_RESET_SECONDS) -> None:
        self.failure_threshold = failure_threshold
        self.reset_seconds = reset_seconds
        self.failure_count = 0
        self.opened_at: float | None = None

    def is_open(self) -> bool:
        if self.opened_at is None:
            return False
        if time.time() - self.opened_at >= self.reset_seconds:
            self.failure_count = 0
            self.opened_at = None
            return False
        return True

    def record_success(self) -> None:
        self.failure_count = 0
        self.opened_at = None

    def record_failure(self) -> None:
        self.failure_count += 1
        if self.failure_count >= self.failure_threshold:
            self.opened_at = time.time()


class LLMService:
    _instance: "LLMService | None" = None

    @classmethod
    def get_instance(cls, api_key: str | None = None, client: Any | None = None, model: str | None = None) -> "LLMService":
        if cls._instance is None:
            from ..config.settings import settings
            key = api_key or settings.groq_api_key
            if not key:
                raise RuntimeError("GROQ_API_KEY is not set in settings or passed to get_instance")
            cls._instance = cls(api_key=key, client=client, model=model)
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    def __init__(self, api_key: str, client: Any | None = None, model: str | None = None) -> None:
        self.model = model or settings.groq_model
        self.client = client or self._create_client(api_key)
        self.circuit_breaker = CircuitBreaker()

    def _create_client(self, api_key: str):
        if Groq is None:
            raise RuntimeError("groq is not installed")
        return Groq(api_key=api_key)

    def _rule_based_fallback(self, prompt: str, reason: str) -> LLMResult:
        return LLMResult(
            text=f"Advisory generated via rule-based engine (AI service temporarily unavailable).\n\n{prompt}",
            generated_via="RULE_BASED",
            fallback_reason=reason,
        )

    def generate(self, prompt: str, system_prompt: str | None = None) -> LLMResult:
        if self.circuit_breaker.is_open():
            return self._rule_based_fallback(prompt, "circuit_open")

        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            response = self.client.chat.completions.create(model=self.model, messages=messages)
            text = response.choices[0].message.content
            self.circuit_breaker.record_success()
            return LLMResult(text=text, generated_via="LLM")
        except Exception as exc:
            self.circuit_breaker.record_failure()
            if self.circuit_breaker.is_open():
                return self._rule_based_fallback(prompt, f"open_after_failure:{exc.__class__.__name__}")
            return self._rule_based_fallback(prompt, f"failure:{exc.__class__.__name__}")


def get_llm():
    from langchain_groq import ChatGroq
    from ..config.settings import settings
    return ChatGroq(
        groq_api_key=settings.groq_api_key,
        model_name=settings.groq_model,
        temperature=0.0,
    )
