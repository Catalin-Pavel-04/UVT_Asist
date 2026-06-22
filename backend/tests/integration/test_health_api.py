from __future__ import annotations

import pytest

import api.routes_health as routes_health
from app import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def test_health_returns_json(monkeypatch, client) -> None:
    monkeypatch.setattr(
        routes_health,
        "build_health_payload",
        lambda: {"status": "degraded", "ready": False, "checks": {"ollama": False}},
    )

    response = client.get("/health")

    assert response.status_code == 200
    assert response.is_json
    assert response.get_json()["status"] == "degraded"


def test_faculties_returns_list(client) -> None:
    response = client.get("/faculties")
    payload = response.get_json()

    assert response.status_code == 200
    assert isinstance(payload["faculties"], list)
    assert {"id": "uvt", "name": "UVT (general)"} in payload["faculties"]
