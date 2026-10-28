import time
from typing import Any

import requests

from .base import LLMConnectionError, LLMError, LLMResponse, Message, ensure_local_url


class LocalHttpChatClient:
    provider = "local_http"

    def __init__(
        self,
        base_url: str,
        model: str = "",
        *,
        allowed_hosts: tuple[str, ...],
        timeout: float = 300.0,
    ):
        ensure_local_url(base_url, allowed_hosts)
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        self._session.trust_env = False
        # Empty until the first request resolves it, so reading it never touches the network.
        self.model = model

    def list_models(self) -> list[str]:
        data = self._request("GET", "/models")
        return [item["id"] for item in data.get("data", [])]

    def complete(
        self,
        messages: list[Message],
        *,
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        if not self.model:
            self.model = self._only_loaded_model()
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        if json_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "extraction", "strict": True, "schema": json_schema},
            }

        started = time.perf_counter()
        data = self._request("POST", "/chat/completions", json=payload)
        seconds = time.perf_counter() - started

        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Unexpected response shape from {self.base_url}") from exc
        return LLMResponse(
            text=text or "",
            model=data.get("model", self.model),
            seconds=seconds,
            usage=data.get("usage") or {},
        )

    def _only_loaded_model(self) -> str:
        models = self.list_models()
        if len(models) == 1:
            return models[0]
        if not models:
            raise LLMError(f"No model is loaded on {self.base_url}. Load one in LM Studio first.")
        raise LLMError(
            f"Several models available on {self.base_url}: {', '.join(models)}. "
            "Choose one with LLM_MODEL or --model."
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = self.base_url + path
        try:
            response = self._session.request(method, url, timeout=self.timeout, **kwargs)
        except requests.ConnectionError as exc:
            raise LLMConnectionError(
                f"Cannot connect to {self.base_url}. Is the local LLM server running "
                "(LM Studio: Developer -> Start Server)?"
            ) from exc
        except requests.Timeout as exc:
            raise LLMConnectionError(
                f"{url} did not answer within {self.timeout}s (LLM_TIMEOUT)."
            ) from exc

        if response.status_code >= 400:
            raise LLMError(f"{method} {url} -> HTTP {response.status_code}: {response.text[:300]}")
        try:
            return response.json()
        except ValueError as exc:
            raise LLMError(f"{url} returned a non-JSON response") from exc
