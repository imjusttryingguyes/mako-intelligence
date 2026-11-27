from fastapi.testclient import TestClient

from mako_intelligence.api.routes import health
from mako_intelligence.main import app

client = TestClient(app)


def test_liveness_without_database() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "mako-api", "version": "0.1.0"}


def test_readiness_success(monkeypatch) -> None:
    monkeypatch.setattr(health, "check_database", lambda: None)
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}


def test_readiness_failure_does_not_leak_secrets(monkeypatch) -> None:
    def failing_probe() -> None:
        raise RuntimeError("postgresql://mako:super-secret@example/db")

    monkeypatch.setattr(health, "check_database", failing_probe)
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json() == {"detail": "database unavailable"}
    assert "super-secret" not in response.text


def test_cors_only_explicit_local_origin() -> None:
    permitted = client.get("/healthz", headers={"Origin": "http://localhost:3000"})
    assert permitted.headers.get("access-control-allow-origin") == "http://localhost:3000"
    blocked = client.get("/healthz", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in blocked.headers
