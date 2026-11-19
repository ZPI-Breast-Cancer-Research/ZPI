import pytest

from workers.extraction.config import DEFAULT_ALLOWED_HOSTS
from workers.extraction.errors import HostNotAllowedError, UnknownComponentError
from workers.extraction.llm import get_llm_client
from workers.extraction.llm.base import ensure_local_url
from workers.extraction.llm.local_http import LocalHttpChatClient
from workers.extraction.utils.plugins import load_class


@pytest.mark.parametrize(
    "url",
    ["http://localhost:1234/v1", "http://127.0.0.1:8000/v1", "http://host.docker.internal:1234/v1"],
)
def test_local_hosts_are_allowed(url):
    # Act / Assert: no exception
    ensure_local_url(url, DEFAULT_ALLOWED_HOSTS)


@pytest.mark.parametrize(
    "url",
    ["https://api.openai.com/v1", "http://localhost.evil.com/v1", "ftp://localhost/v1"],
)
def test_other_hosts_and_schemes_are_refused(url):
    # Act / Assert
    with pytest.raises(HostNotAllowedError):
        ensure_local_url(url, DEFAULT_ALLOWED_HOSTS)


def test_client_refuses_remote_url_before_any_request():
    # Act / Assert
    with pytest.raises(HostNotAllowedError, match="api.example.com"):
        LocalHttpChatClient("https://api.example.com/v1", allowed_hosts=DEFAULT_ALLOWED_HOSTS)


def test_client_ignores_proxy_environment_variables():
    # Act
    client = LocalHttpChatClient("http://localhost:1234/v1", allowed_hosts=DEFAULT_ALLOWED_HOSTS)

    # Assert
    assert client._session.trust_env is False


def test_load_class_imports_registered_target():
    # Act
    cls = load_class(
        {"local_http": ".local_http:LocalHttpChatClient"},
        "local_http",
        "LLM provider",
        "workers.extraction.llm",
        setting="LLM_PROVIDER",
    )

    # Assert
    assert cls is LocalHttpChatClient


def test_unknown_component_lists_available_names_and_setting():
    # Act / Assert
    with pytest.raises(UnknownComponentError, match=r"'nope'.*LLM_PROVIDER.*local_http"):
        get_llm_client("nope")
