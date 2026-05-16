"""OpenAI-compatible LLM client and JSON parsing helpers for the source KG compiler."""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


class OpenAICompatibleSourceKGLLM:
    """Small OpenAI-compatible JSON client with usage accounting."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 8192,
    ) -> None:
        load_source_kg_env()
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY") or os.environ.get(
            "OPENAI_API_KEY"
        )
        self.base_url = (
            base_url
            or os.environ.get("DEEPSEEK_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
            or "https://api.deepseek.com"
        )
        self.model = (
            model
            or os.environ.get("DEEPSEEK_MODEL")
            or os.environ.get("OPENAI_MODEL")
            or "deepseek-v4-flash"
        )
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self._client: Any | None = None
        self._lock = threading.Lock()

    @property
    def total_tokens(self) -> int:
        """Return total recorded provider tokens."""
        with self._lock:
            return self.input_tokens + self.output_tokens

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> str:
        """Call the configured chat model and return raw JSON text."""
        if not self.api_key:
            raise ValueError(
                "Missing LLM API key. Set DEEPSEEK_API_KEY or OPENAI_API_KEY, "
                "or configure .env.local/.env."
            )
        kwargs: dict[str, Any] = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
        }
        if "deepseek" in f"{self.base_url} {self.model}".lower():
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        completion = self._resolved_client().chat.completions.create(**kwargs)
        usage = getattr(completion, "usage", None)
        with self._lock:
            self.calls += 1
            if usage is not None:
                self.input_tokens += int(getattr(usage, "prompt_tokens", 0) or 0)
                self.output_tokens += int(getattr(usage, "completion_tokens", 0) or 0)
        content = completion.choices[0].message.content
        if not content:
            raise ValueError("LLM returned empty content")
        return str(content)

    def repair_json(self, broken_json: str, error: str) -> str:
        """Ask the same model to repair invalid JSON."""
        return self.complete_json(
            system_prompt="You repair invalid JSON. Return JSON only, no markdown.",
            user_prompt=(
                "The following text was intended to be JSON but failed to parse.\n"
                f"Parser error: {error}\n\n"
                "Return a valid JSON object or array preserving the intended fields.\n\n"
                f"{broken_json}"
            ),
        )

    def _resolved_client(self) -> Any:
        if self._client is not None:
            return self._client
        with self._lock:
            if self._client is not None:
                return self._client
            try:
                from openai import OpenAI
            except ImportError as exc:  # pragma: no cover - optional dependency guard.
                raise ImportError("Install the llm extra with: uv sync --extra llm") from exc
            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            return self._client


def load_source_kg_env() -> None:
    """Load common local env files without overriding the shell."""
    for path in (
        Path(".env.local"),
        Path(".env"),
        Path.home() / "code" / "KGTraceVis" / ".env.local",
    ):
        if path.is_file():
            load_dotenv(path, override=False)


def safe_json_parse(
    text: str,
    *,
    repairer: Any | None = None,
    max_retries: int = 2,
) -> Any:
    """Parse model JSON with fence stripping, slicing, and optional repair."""
    current = _strip_json_fence(text)
    last_error = ""
    for attempt in range(max_retries + 1):
        for candidate in _json_candidates(current):
            try:
                return json.loads(candidate)
            except json.JSONDecodeError as exc:
                last_error = str(exc)
        if repairer is None or attempt >= max_retries:
            break
        current = repairer(current, last_error)
    raise ValueError(f"Could not parse JSON after {max_retries} repair retries: {last_error}")


def _strip_json_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _json_candidates(text: str) -> list[str]:
    candidates = [text.strip()]
    object_start = text.find("{")
    object_end = text.rfind("}")
    if 0 <= object_start < object_end:
        candidates.append(text[object_start : object_end + 1])
    array_start = text.find("[")
    array_end = text.rfind("]")
    if 0 <= array_start < array_end:
        candidates.append(text[array_start : array_end + 1])
    return [candidate for candidate in candidates if candidate]
