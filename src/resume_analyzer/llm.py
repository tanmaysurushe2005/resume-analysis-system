"""LLM access (Anthropic or Gemini) with strict JSON validation and a self-repair retry loop."""
from __future__ import annotations

import json
import os
import re
import sys
import time
from time import perf_counter
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from .usage import UsageTracker
from .ratelimit import DailyLimitReached, RateLimiter

T = TypeVar("T", bound=BaseModel)


def extract_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip())
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ValueError("no JSON object found in model output")
    return json.loads(text[start:end + 1])


class LLM:
    """Base class: subclasses implement complete(); json_call adds validation + repair."""

    name = "base"

    def __init__(self):
        self.usage = UsageTracker()

    def complete(self, task: str, system: str, messages: list[dict],
                 max_tokens: int = 4000, temperature: float = 0.0,
                 response_schema: type[BaseModel] | None = None) -> str:
        raise NotImplementedError

    def json_call(self, task: str, system: str, user: str, model_cls: type[T],
                  retries: int = 1, max_tokens: int = 4000) -> T:
        messages = [{"role": "user", "content": user}]
        last_err = ""
        for _ in range(retries + 1):
            raw = self.complete(
                task, system, messages, max_tokens=max_tokens,
                response_schema=model_cls,
            )
            try:
                return model_cls.model_validate(extract_json(raw))
            except (ValueError, ValidationError) as err:
                last_err = str(err)[:600]
                messages = messages[:1] + [
                    {"role": "assistant", "content": raw or ""},
                    {"role": "user", "content":
                        "Your reply was not valid for the schema: " + last_err +
                        "\nReturn ONLY the corrected JSON object."},
                ]
        raise RuntimeError(f"[{task}] no valid JSON after {retries + 1} attempts: {last_err}")


class AnthropicLLM(LLM):
    def __init__(self, model: str):
        import anthropic  # imported lazily so other modes need no SDK

        super().__init__()
        self.rate_limiter = RateLimiter()
        self.client = anthropic.Anthropic()
        self.model = model
        self.name = model

    def complete(self, task, system, messages, max_tokens=4000, temperature=0.0,
                 response_schema=None):
        kwargs = dict(model=self.model, system=system, messages=messages, max_tokens=max_tokens)
        # Newer models may reject temperature, so send it only when explicitly configured.
        if os.getenv("RA_TEMPERATURE"):
            kwargs["temperature"] = float(os.getenv("RA_TEMPERATURE"))
        started = perf_counter()
        self.rate_limiter.acquire()
        resp = self.client.messages.create(**kwargs)
        usage = getattr(resp, "usage", None)
        self.usage.record(
            task=task,
            model=self.model,
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
            latency_ms=(perf_counter() - started) * 1000,
        )
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


class GeminiLLM(LLM):
    def __init__(self, api_key: str, model: str):
        from google import genai  # imported lazily so other modes need no SDK

        super().__init__()
        self.rate_limiter = RateLimiter()
        timeout_ms = int(os.getenv("RA_API_TIMEOUT_MS", "60000"))
        self.client = genai.Client(
            api_key=api_key,
            http_options={"timeout": timeout_ms},
        )
        self.model = model
        self.name = model

    def complete(self, task, system, messages, max_tokens=4000, temperature=0.0,
                 response_schema=None):
        from google.genai import types

        contents = [
            {
                "role": "model" if message["role"] == "assistant" else "user",
                "parts": [{"text": message["content"]}],
            }
            for message in messages
        ]
        thinking_budget = int(os.getenv("RA_GEMINI_THINKING_BUDGET", "0"))
        config = {
            "system_instruction": system,
            "response_mime_type": "application/json",
            "max_output_tokens": max_tokens,
            "thinking_config": types.ThinkingConfig(thinking_budget=thinking_budget),
        }
        if response_schema is not None:
            config["response_schema"] = response_schema
        if os.getenv("RA_TEMPERATURE"):
            config["temperature"] = float(os.getenv("RA_TEMPERATURE"))

        schema_fallback = False
        thinking_fallback = False
        for attempt in range(6):  # back off on free-tier rate limits / overload
            try:
                print(
                    f"[gemini] {task}: request {attempt + 1}/6",
                    file=sys.stderr,
                    flush=True,
                )
                started = perf_counter()
                self.rate_limiter.acquire()
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=config,
                )
                usage = getattr(response, "usage_metadata", None)
                self.usage.record(
                    task=task,
                    model=self.model,
                    input_tokens=getattr(usage, "prompt_token_count", 0) or 0,
                    output_tokens=getattr(usage, "candidates_token_count", 0) or 0,
                    thinking_tokens=getattr(usage, "thoughts_token_count", 0) or 0,
                    latency_ms=(perf_counter() - started) * 1000,
                )
                return response.text or ""
            except Exception as err:  # noqa: BLE001
                text = str(err).upper()
                if (
                    response_schema is not None
                    and not schema_fallback
                    and ("SCHEMA" in text or "STRUCTURED" in text)
                ):
                    config.pop("response_schema", None)
                    schema_fallback = True
                    continue
                if (
                    thinking_budget == 0
                    and not thinking_fallback
                    and ("THINKING" in text or "THOUGHT" in text)
                ):
                    config.pop("thinking_config", None)
                    thinking_fallback = True
                    continue
                status_code = getattr(err, "status_code", None) or getattr(err, "code", None)
                retryable = (
                    status_code in (429, 503)
                    or "RESOURCE_EXHAUSTED" in text
                    or "429" in text
                    or "503" in text
                )
                daily_quota_exhausted = (
                    "PER DAY" in text
                    or "PER_DAY" in text
                    or "GENERATE_CONTENT_FREE_TIER_REQUESTS" in text
                )
                if daily_quota_exhausted:
                    raise DailyLimitReached(
                        f"Gemini daily quota is exhausted for model {self.model}. "
                        "Use RA_MOCK=1, wait for the quota reset, or enable billing/use "
                        "a project with available Gemini quota."
                    ) from err
                if not retryable or attempt == 5:
                    raise
                print(
                    f"[gemini] {task}: retrying after rate limit/server error "
                    f"in {15 * (attempt + 1)}s",
                    file=sys.stderr,
                    flush=True,
                )
                time.sleep(15 * (attempt + 1))
        return ""


def get_llm() -> LLM:
    """Select the configured provider, or use the clearly announced offline mock."""
    try:
        from dotenv import load_dotenv
        load_dotenv(override=True)
    except ImportError:
        pass

    if os.getenv("RA_MOCK") == "1":
        from .mock import MockLLM
        return MockLLM()

    provider = os.getenv("RA_PROVIDER", "").lower()
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")

    if provider == "gemini" and not gemini_key:
        raise SystemExit("RA_PROVIDER=gemini but GEMINI_API_KEY was not found. "
                         "Check that .env is in the project root and the variable name is exact.")
    if gemini_key and (provider == "gemini" or (not provider and not anthropic_key)):
        return GeminiLLM(gemini_key, os.getenv("RA_GEMINI_MODEL", "gemini-2.5-flash"))
    if anthropic_key:
        return AnthropicLLM(os.getenv("RA_MODEL", "claude-sonnet-5-5"))

    from .mock import MockLLM
    print("[note] Running in OFFLINE MOCK mode (keyword heuristics, not a real model). "
          "Set GEMINI_API_KEY (with RA_PROVIDER=gemini) or ANTHROPIC_API_KEY for real analysis.",
          file=sys.stderr)
    return MockLLM()