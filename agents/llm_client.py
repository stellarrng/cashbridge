"""LLM client with a deterministic offline fallback (instructions.md section 3, Rule 1).

The client wraps any OpenAI-compatible API (``LLM_BASE_URL``, ``LLM_MODEL``,
``LLM_API_KEY``), so DeepSeek or Qwen can be used in mainland China. It never asks the
model to calculate anything. Every call follows the same path:

  1. PII is masked and untrusted text is wrapped as quoted data.
  2. The provider is called with an 8 second timeout.
  3. The reply must parse into the caller's Pydantic schema.
  4. Free text must pass the number lock (``security.number_check``).
  5. Any failure at any step returns the caller's deterministic fallback instead.

With no API key the provider is never called. After a failure the client stays in
``offline-demo`` mode until ``reset()`` is called, so the demo is not left half-live.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Type, TypeVar, Union

from pydantic import BaseModel

from config import settings
from security import injection_guard, number_check
from security.pii_masker import PiiMasker

OFFLINE = "offline-demo"
LIVE = "live-llm"

T = TypeVar("T", bound=BaseModel)
Provider = Callable[[List[Dict[str, str]], str, float], str]
Fallback = Union[BaseModel, Callable[[], BaseModel]]


@dataclass
class StructuredResult:
    """The validated object, which mode produced it and, if a fallback ran, why."""

    value: BaseModel
    mode: str
    reason: Optional[str] = None

    @property
    def used_fallback(self) -> bool:
        return self.reason is not None


def openai_provider(base_url: str, api_key: str) -> Provider:
    """Provider backed by the ``openai`` SDK. The import happens only when a key is set."""

    def call(messages: List[Dict[str, str]], model: str, timeout: float) -> str:
        from openai import OpenAI

        client = OpenAI(base_url=base_url or None, api_key=api_key, timeout=timeout, max_retries=0)
        reply = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0,
        )
        return reply.choices[0].message.content or ""

    return call


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _strings(item)


def _map_strings(value: Any, func: Callable[[str], str]) -> Any:
    if isinstance(value, str):
        return func(value)
    if isinstance(value, dict):
        return {k: _map_strings(v, func) for k, v in value.items()}
    if isinstance(value, list):
        return [_map_strings(v, func) for v in value]
    return value


class LlmClient:
    """One client per process. Provider, key and timeout are injectable for tests."""

    def __init__(
        self,
        base_url: str = settings.LLM_BASE_URL,
        model: str = settings.LLM_MODEL,
        api_key: str = settings.LLM_API_KEY,
        timeout: float = settings.LLM_TIMEOUT_SECONDS,
        provider: Optional[Provider] = None,
    ) -> None:
        self._model = model
        self._api_key = api_key.strip()
        self._timeout = timeout
        self._provider = provider
        self._base_url = base_url
        self._degraded = False
        self._masker = PiiMasker()

    # ------------------------------------------------------------------ state
    def current_mode(self) -> str:
        """``live-llm`` only when a key is set and no call has failed since the last reset."""
        return LIVE if self._api_key and not self._degraded else OFFLINE

    def reset(self) -> None:
        """Try the live provider again on the next call."""
        self._degraded = False

    def pii_inspector(self) -> Dict[str, str]:
        """Before/after text of the last masked call, for the UI PII inspector."""
        return self._masker.inspector()

    # ------------------------------------------------------------------- call
    def complete_structured(
        self,
        prompt: str,
        schema: Type[T],
        fallback: Fallback,
        *,
        untrusted: Optional[str] = None,
        untrusted_source: str = "email",
        directory: Optional[Mapping[str, Iterable[str]]] = None,
        locked_metrics: Optional[Mapping[str, Any]] = None,
        check_numbers: bool = True,
    ) -> StructuredResult:
        """Return a ``schema`` object from the model, or from ``fallback`` if anything fails.

        ``untrusted`` is outside text (email, PDF, reply): it is masked and wrapped as data.
        ``locked_metrics`` are the only numbers free text may contain. Pass
        ``check_numbers=False`` for pure field extraction where numbers come from a document.
        """
        if not self._api_key:
            return self._fall_back(fallback, "no API key: offline mode")
        if self._degraded:
            return self._fall_back(fallback, "earlier provider failure: offline mode")

        try:
            messages, token_map = self._build_messages(prompt, schema, untrusted, untrusted_source, directory)
            provider = self._provider or openai_provider(self._base_url, self._api_key)
            raw = provider(messages, self._model, self._timeout)
        except Exception as error:  # timeout, network, SDK or auth error
            self._degraded = True
            return self._fall_back(fallback, f"provider error: {type(error).__name__}")

        try:
            data = json.loads(raw)
            data = _map_strings(data, lambda text: PiiMasker.unmask(text, token_map))
            value = schema.model_validate(data)
        except Exception as error:  # invalid JSON or schema mismatch
            return self._fall_back(fallback, f"schema failure: {type(error).__name__}")

        if check_numbers:
            text = " ".join(_strings(value.model_dump(mode="json")))
            verdict = number_check.check(text, locked_metrics or {})
            if not verdict.ok:
                return self._fall_back(fallback, f"number check rejected: {', '.join(verdict.offending)}")
        return StructuredResult(value=value, mode=LIVE)

    # --------------------------------------------------------------- internals
    def _build_messages(
        self,
        prompt: str,
        schema: Type[BaseModel],
        untrusted: Optional[str],
        source: str,
        directory: Optional[Mapping[str, Iterable[str]]],
    ):
        masked_prompt, token_map = self._masker.mask(prompt, directory)
        user = masked_prompt
        if untrusted:
            masked_data, data_map = self._masker.mask(untrusted, directory)
            token_map = {**token_map, **data_map}
            user = f"{masked_prompt}\n\n{injection_guard.wrap(masked_data, source)}"
        system = (
            "You are a finance assistant. Reply with exactly one JSON object that matches this "
            f"JSON schema: {json.dumps(schema.model_json_schema())}. Output JSON only. "
            "Never calculate, estimate or invent numbers; use only numbers given in the input. "
            "Use null and a reason for anything missing."
        )
        return [{"role": "system", "content": system}, {"role": "user", "content": user}], token_map

    @staticmethod
    def _fall_back(fallback: Fallback, reason: str) -> StructuredResult:
        value = fallback() if callable(fallback) else fallback
        return StructuredResult(value=value, mode=OFFLINE, reason=reason)


def get_client() -> LlmClient:
    """Client configured from the environment."""
    return LlmClient()
