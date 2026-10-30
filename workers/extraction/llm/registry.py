from ..config import Settings
from ..plugins import load_class
from .base import LLMClient

PROVIDERS = {
    "local_http": ".local_http:LocalHttpChatClient",
}


def get_llm_client(settings: Settings) -> LLMClient:
    cls = load_class(PROVIDERS, settings.llm_provider, "LLM provider", __package__)
    return cls(
        settings.llm_base_url,
        settings.llm_model,
        allowed_hosts=settings.llm_allowed_hosts,
        timeout=settings.llm_timeout,
    )
