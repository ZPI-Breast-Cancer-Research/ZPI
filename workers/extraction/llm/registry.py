from typing import Any

from ..plugins import load_class
from .base import LLMClient

PROVIDERS = {
    "local_http": ".local_http:LocalHttpChatClient",
}


def get_llm_client(name: str, **options: Any) -> LLMClient:
    return load_class(PROVIDERS, name, "LLM provider", __package__)(**options)
