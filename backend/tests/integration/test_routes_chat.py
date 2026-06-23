from __future__ import annotations

import pytest
from flask import Flask

import api.routes_chat as routes_chat


@pytest.fixture()
def client():
    app = Flask(__name__)
    app.config.update(TESTING=True)
    app.register_blueprint(routes_chat.bp)
    return app.test_client()


def test_chat_route_calls_handle_chat_and_returns_status(monkeypatch, client) -> None:
    calls = {}

    def fake_handle_chat(payload):
        calls["payload"] = payload
        return {"answer": "ok", "confidence": "high"}, 202

    telemetry_calls = []
    monkeypatch.setattr(routes_chat, "new_request_id", lambda: "req-route")
    monkeypatch.setattr(routes_chat, "handle_chat", fake_handle_chat)
    monkeypatch.setattr(
        routes_chat,
        "log_chat_request",
        lambda request_id, request_payload, response_payload, total_latency_ms: telemetry_calls.append(
            (request_id, request_payload, response_payload, total_latency_ms)
        ),
    )

    response = client.post("/chat", json={"question": "Unde gasesc orarul?", "faculty_id": "info"})

    assert response.status_code == 202
    assert response.get_json() == {"answer": "ok", "confidence": "high"}
    assert calls["payload"] == {"question": "Unde gasesc orarul?", "faculty_id": "info"}
    assert telemetry_calls
    assert telemetry_calls[0][0] == "req-route"
    assert telemetry_calls[0][1]["faculty_id"] == "info"
    assert telemetry_calls[0][2]["answer"] == "ok"
    assert isinstance(telemetry_calls[0][3], int)


def test_chat_route_logs_exception_when_handle_chat_raises(monkeypatch, client) -> None:
    logged = {}
    error = RuntimeError("chat failed")

    def fake_handle_chat(payload):
        raise error

    def fake_log_chat_exception(request_id, request_payload, total_latency_ms, exc):
        logged["request_id"] = request_id
        logged["request_payload"] = request_payload
        logged["total_latency_ms"] = total_latency_ms
        logged["exc"] = exc

    monkeypatch.setattr(routes_chat, "new_request_id", lambda: "req-exception")
    monkeypatch.setattr(routes_chat, "handle_chat", fake_handle_chat)
    monkeypatch.setattr(routes_chat, "log_chat_exception", fake_log_chat_exception)

    with pytest.raises(RuntimeError, match="chat failed"):
        client.post("/chat", json={"question": "Test", "faculty_id": "uvt"})

    assert logged["request_id"] == "req-exception"
    assert logged["request_payload"] == {"question": "Test", "faculty_id": "uvt"}
    assert isinstance(logged["total_latency_ms"], int)
    assert logged["exc"] is error
