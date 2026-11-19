"""The real HTTP LLM client against a stub OpenAI-compatible server on localhost."""

import socket

import pytest

from workers.extraction.config import Settings
from workers.extraction.errors import LLMConnectionError, LLMError
from workers.extraction.llm.local_http import LocalHttpChatClient
from workers.extraction.pipeline import Extractor
from workers.extraction.tests.factories import REPORT, answer_json, extraction

LOCAL = ("127.0.0.1",)
MESSAGES = [{"role": "user", "content": "Opis badania: zmiana 5 mm"}]


def client(server, model="stub-model"):
    return LocalHttpChatClient(server.base_url, model, allowed_hosts=LOCAL, timeout=5)


def test_request_payload_with_json_schema(llm_server):
    # Arrange
    llm_server.reply("{}")
    schema = {"type": "object"}

    # Act
    response = client(llm_server).complete(MESSAGES, json_schema=schema)

    # Assert
    sent = llm_server.requests[0]["json"]
    assert sent["model"] == "stub-model"
    assert sent["messages"] == MESSAGES
    assert sent["temperature"] == 0.0
    assert sent["stream"] is False
    assert sent["response_format"]["json_schema"]["schema"] == schema
    assert sent["response_format"]["json_schema"]["strict"] is True
    assert response.text == "{}"
    assert response.usage == {"prompt_tokens": 10, "completion_tokens": 5}


def test_request_without_json_schema_has_no_response_format(llm_server):
    # Arrange
    llm_server.reply("{}")

    # Act
    client(llm_server).complete(MESSAGES)

    # Assert
    assert "response_format" not in llm_server.requests[0]["json"]


def test_list_models(llm_server):
    # Arrange
    llm_server.models = ["a", "b"]

    # Act / Assert
    assert client(llm_server).list_models() == ["a", "b"]


def test_empty_model_picks_the_only_loaded_one(llm_server):
    # Arrange
    llm_server.reply("{}", model="stub-model")
    llm = client(llm_server, model="")

    # Act
    llm.complete(MESSAGES)

    # Assert
    assert llm.model == "stub-model"
    assert llm_server.requests[0]["json"]["model"] == "stub-model"


@pytest.mark.parametrize(
    ("models", "message"),
    [(["a", "b"], "Several models available"), ([], "No model is loaded")],
)
def test_empty_model_needs_exactly_one_loaded(llm_server, models, message):
    # Arrange
    llm_server.models = models

    # Act / Assert
    with pytest.raises(LLMError, match=message):
        client(llm_server, model="").complete(MESSAGES)


@pytest.mark.parametrize(
    ("status", "body", "message"),
    [
        (500, "internal error", "HTTP 500"),
        (200, "<html>nie json</html>", "non-JSON response"),
        (200, '{"choices": []}', "Unexpected response shape"),
    ],
    ids=["http-error", "not-json", "wrong-shape"],
)
def test_bad_server_answers_raise_llm_error(llm_server, status, body, message):
    # Arrange
    llm_server.reply_raw(status, body)

    # Act / Assert
    with pytest.raises(LLMError, match=message):
        client(llm_server).complete(MESSAGES)


def test_server_not_running_raises_connection_error():
    # Arrange: a port nobody listens on.
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    llm = LocalHttpChatClient(f"http://127.0.0.1:{port}/v1", "m", allowed_hosts=LOCAL, timeout=5)

    # Act / Assert
    with pytest.raises(LLMConnectionError, match="Cannot connect"):
        llm.complete(MESSAGES)


def test_extractor_from_settings_extracts_over_http(llm_server):
    # Arrange
    llm_server.reply(answer_json())
    settings = Settings(llm_base_url=llm_server.base_url, llm_allowed_hosts=LOCAL, llm_model="")

    # Act
    result = Extractor.from_settings(settings).extract_text(REPORT, source="doc1.txt")

    # Assert
    assert result.status == "ok"
    assert result.data == extraction()
    assert result.provenance.llm_provider == "local_http"
    assert result.provenance.llm_model == "stub-model"
