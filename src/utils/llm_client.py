"""
Generic OpenAI-compatible LLM client.

Design goals:
- Provider-agnostic (DeepSeek/any OpenAI-compatible endpoint)
- Soft-fail: never raise for LLM errors; allow rules fallback
- Audit-friendly: produce a per-request trace_id + model metadata (no secrets)
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from dataclasses import dataclass
from typing import Optional, Type

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LLMConfig:
    api_key: str
    base_url: str
    model: str

    @property
    def provider(self) -> str:
        try:
            host = re.sub(r"^https?://", "", (self.base_url or "").strip()).split("/")[0]
            return host or "openai-compatible"
        except Exception:
            return "openai-compatible"


@dataclass
class LLMCallMeta:
    trace_id: str
    provider: str
    base_url: str
    model: str


class LLMClient:
    def __init__(self, force_disabled: bool = False):
        self._force_disabled = force_disabled
        self._config = self._load_config()
        self._last_meta: Optional[LLMCallMeta] = None

    def is_configured(self) -> bool:
        if self._force_disabled:
            return False
        if (os.environ.get("LLM_DISABLED") or "").strip().lower() in {"1", "true", "yes"}:
            return False
        return bool(self._config and self._config.api_key and self._config.base_url and self._config.model)

    def get_last_meta(self) -> Optional[LLMCallMeta]:
        return self._last_meta

    def get_config_meta(self) -> Optional[dict]:
        if not self._config:
            return None
        return {
            "provider": self._config.provider,
            "base_url": self._config.base_url,
            "model": self._config.model,
        }

    def generate_text(self, prompt: str, retries: int = 1) -> Optional[str]:
        trace_id = str(uuid.uuid4())
        self._set_last_meta(trace_id)

        if not self.is_configured():
            logger.info("LLM not configured; skipping generate_text")
            return None

        messages = [
            {"role": "system", "content": "You are a careful assistant. Return only the requested content."},
            {"role": "user", "content": prompt},
        ]

        for attempt in range(max(1, retries + 1)):
            try:
                content = self._chat(messages=messages, response_format=None)
                if content and content.strip():
                    return content.strip()
            except Exception as e:
                logger.warning("LLM generate_text failed (attempt %s/%s): %s", attempt + 1, retries + 1, e)
        return None

    def generate_structured_data(
        self, prompt: str, pydantic_model: Type[BaseModel], retries: int = 2
    ) -> Optional[BaseModel]:
        trace_id = str(uuid.uuid4())
        self._set_last_meta(trace_id)

        if not self.is_configured():
            logger.info("LLM not configured; skipping generate_structured_data")
            return None

        schema_hint = ""
        try:
            schema_hint = json.dumps(pydantic_model.model_json_schema(), ensure_ascii=False, indent=2)
        except Exception:
            schema_hint = ""

        base_messages = [
            {
                "role": "system",
                "content": (
                    "You are a careful assistant.\n"
                    "Return ONLY valid JSON (no markdown, no code fences, no commentary).\n"
                    "The JSON must conform to the provided JSON Schema."
                ),
            },
            {
                "role": "user",
                "content": f"{prompt}\n\nJSON Schema:\n{schema_hint}",
            },
        ]

        last_raw: Optional[str] = None
        for attempt in range(max(1, retries + 1)):
            try:
                raw = self._chat(messages=base_messages, response_format={"type": "json_object"})
                last_raw = raw
                parsed = self._parse_json_safely(raw)
                if parsed is None:
                    raise ValueError("JSON parse failed")
                return pydantic_model.model_validate(parsed)
            except (ValidationError, ValueError, json.JSONDecodeError) as e:
                logger.warning(
                    "LLM structured output invalid (attempt %s/%s): %s", attempt + 1, retries + 1, e
                )
            except Exception as e:
                logger.warning(
                    "LLM generate_structured_data failed (attempt %s/%s): %s", attempt + 1, retries + 1, e
                )

        # One JSON repair pass (no further retries)
        if last_raw:
            repaired = self._repair_json(last_raw, schema_hint)
            if repaired:
                try:
                    parsed = self._parse_json_safely(repaired)
                    if parsed is None:
                        return None
                    return pydantic_model.model_validate(parsed)
                except Exception as e:
                    logger.warning("LLM JSON repair still invalid: %s", e)

        return None

    # ---- internal ----
    def _load_config(self) -> Optional[LLMConfig]:
        if self._force_disabled:
            return None
        try:
            from dotenv import load_dotenv  # type: ignore

            load_dotenv()
        except Exception:
            # dotenv is optional at runtime; env vars still work.
            pass

        if (os.environ.get("LLM_DISABLED") or "").strip().lower() in {"1", "true", "yes"}:
            return None

        api_key = (os.environ.get("LLM_API_KEY") or "").strip()
        base_url = (os.environ.get("LLM_BASE_URL") or "").strip()
        model = (os.environ.get("LLM_MODEL") or "").strip()

        if not api_key or not base_url or not model:
            return None

        return LLMConfig(api_key=api_key, base_url=base_url, model=model)

    def _set_last_meta(self, trace_id: str) -> None:
        cfg = self._config
        if not cfg:
            self._last_meta = LLMCallMeta(
                trace_id=trace_id,
                provider="openai-compatible",
                base_url=os.environ.get("LLM_BASE_URL", "") or "",
                model=os.environ.get("LLM_MODEL", "") or "",
            )
            return
        self._last_meta = LLMCallMeta(
            trace_id=trace_id, provider=cfg.provider, base_url=cfg.base_url, model=cfg.model
        )

    def _chat(self, messages: list, response_format: Optional[dict]) -> str:
        # Avoid importing heavy SDK unless configured
        if not self._config:
            raise RuntimeError("LLM config missing")

        try:
            from openai import OpenAI  # type: ignore
        except Exception as e:
            raise RuntimeError(f"openai sdk not available: {e}") from e

        client = OpenAI(api_key=self._config.api_key, base_url=self._config.base_url)

        kwargs = {
            "model": self._config.model,
            "messages": messages,
            "temperature": 0.2,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format

        resp = client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""

    def _parse_json_safely(self, text: str) -> Optional[dict]:
        if not text:
            return None
        text = text.strip()
        try:
            return json.loads(text)
        except Exception:
            pass

        # Extract the largest JSON object substring
        try:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                return json.loads(text[start : end + 1])
        except Exception:
            return None
        return None

    def _repair_json(self, bad_output: str, schema_hint: str) -> Optional[str]:
        trace_id = str(uuid.uuid4())
        self._set_last_meta(trace_id)

        prompt = (
            "The following output is supposed to be JSON but is invalid.\n"
            "Return ONLY corrected JSON that conforms to the JSON Schema.\n\n"
            f"JSON Schema:\n{schema_hint}\n\n"
            f"Bad output:\n{bad_output}"
        )
        return self.generate_text(prompt, retries=1)
