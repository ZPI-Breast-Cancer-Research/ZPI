from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urlparse

Message = dict[str, str]


class LLMError(Exception):
    pass


class LLMConnectionError(LLMError):
    pass


class HostNotAllowedError(LLMError):
    pass


@dataclass
class LLMResponse:
    text: str
    model: str
    seconds: float
    usage: dict[str, Any] = field(default_factory=dict)


class LLMClient(Protocol):
    provider: str
    model: str

    def complete(
        self,
        messages: list[Message],
        *,
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse: ...


def ensure_local_url(url: str, allowed_hosts: tuple[str, ...]) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise HostNotAllowedError(f"Unsupported URL scheme in {url!r}")
    if parsed.hostname not in allowed_hosts:
        raise HostNotAllowedError(
            f"LLM host {parsed.hostname!r} is not allowed (allowed: {', '.join(allowed_hosts)}). "
            "Report data must stay on local infrastructure; add a host to LLM_ALLOWED_HOSTS "
            "only if it is a trusted on-premise server."
        )
