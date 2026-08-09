"""
Automated tests for health and readiness/config endpoints.
"""

from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app, base_url="http://127.0.0.1:8000")


def test_health_endpoints():
    """Verify GET /health and GET /api/v1/health return ok status."""
    res1 = client.get("/health", headers={"Host": "127.0.0.1:8000"})
    assert res1.status_code == 200
    assert res1.json()["status"] == "ok"

    res2 = client.get("/api/v1/health", headers={"Host": "127.0.0.1:8000"})
    assert res2.status_code == 200
    assert res2.json()["status"] == "ok"


def test_config_status_endpoints():
    """Verify config status asserts loopback binding, redacted secrets, and Mail.Send prohibition."""
    response = client.get("/api/v1/config/status", headers={"Host": "127.0.0.1:8000"})
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "ready"
    assert data["bound_address"] == "127.0.0.1"
    assert data["mail_send_prohibited"] is True
    assert data["secrets_redacted"] is True
    assert "Mail.Send PROHIBITED" in data["graph_permissions"]
