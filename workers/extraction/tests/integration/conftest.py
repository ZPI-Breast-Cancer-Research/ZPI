import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from workers.extraction.schema import ExtractionResult
from workers.extraction.tests.factories import REPORT, extraction


class StubLLMServer:
    """OpenAI-compatible server on 127.0.0.1 that answers from a script (no real model)."""

    def __init__(self) -> None:
        self.models = ["stub-model"]
        self.replies: list[tuple[int, str]] = []
        self.requests: list[dict[str, Any]] = []
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        # A short poll interval: shutdown() waits for it, once per test.
        self._thread = threading.Thread(
            target=self._server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True
        )

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}/v1"

    def reply(self, content: str, *, model: str = "stub-model") -> None:
        """Queue a normal chat completion whose message content is ``content``."""
        body = {
            "model": model,
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
        self.replies.append((200, json.dumps(body)))

    def reply_raw(self, status: int, body: str) -> None:
        self.replies.append((status, body))

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.path == "/v1/models":
                    self._send(200, json.dumps({"data": [{"id": m} for m in stub.models]}))
                else:
                    self._send(404, "not found")

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length) or b"{}")
                stub.requests.append({"path": self.path, "json": body})
                if self.path != "/v1/chat/completions":
                    self._send(404, "not found")
                elif not stub.replies:
                    self._send(500, "no scripted reply")
                else:
                    self._send(*stub.replies.pop(0))

            def _send(self, status: int, body: str) -> None:
                data = body.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                pass  # keep test output clean

        return Handler


@pytest.fixture
def llm_server():
    server = StubLLMServer()
    server.start()
    yield server
    server.stop()


def write_predictions(path: Path, results: list[ExtractionResult]) -> Path:
    path.write_text("".join(r.model_dump_json() + "\n" for r in results), encoding="utf-8")
    return path


@pytest.fixture
def gold_dir(tmp_path):
    """Two synthetic gold documents (doc1, doc2) and the transcript of doc1."""
    directory = tmp_path / "gold"
    (directory / "text").mkdir(parents=True)
    for key in ("doc1", "doc2"):
        gold = {"source": f"{key}.jpg", "data": extraction().model_dump(mode="json")}
        (directory / f"{key}.json").write_text(
            json.dumps(gold, ensure_ascii=False), encoding="utf-8"
        )
    (directory / "text" / "doc1.txt").write_text(REPORT, encoding="utf-8")
    return directory
