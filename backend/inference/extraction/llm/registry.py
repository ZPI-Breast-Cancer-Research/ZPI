from importlib import import_module

from ..config import Settings
from .base import LLMClient

PROVIDERS = {
    "local_http": ".local_http:LocalHttpChatClient",
}


def get_llm_client(settings: Settings) -> LLMClient:
    try:
        target = PROVIDERS[settings.llm_provider]
    except KeyError:
        raise ValueError(
            f"Unknown LLM provider {settings.llm_provider!r}; available: {', '.join(PROVIDERS)}"
        ) from None
    module_name, class_name = target.split(":")
    cls = getattr(import_module(module_name, __package__), class_name)
    return cls(
        settings.llm_base_url,
        settings.llm_model,
        allowed_hosts=settings.llm_allowed_hosts,
        timeout=settings.llm_timeout,
    )
