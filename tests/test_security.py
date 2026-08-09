"""
Automated tests for loopback security controls:
- Host header rejection (non-loopback -> 403)
- Origin & Referer rejection (non-loopback -> 403)
- CSRF token validation & rejection (invalid/missing token -> 403)
"""

import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.api.routes import security_service

client = TestClient(app, base_url="http://127.0.0.1:8000")


def test_host_header_allowed_loopback():
    """Verify loopback Host headers (127.0.0.1, localhost) are accepted."""
    response = client.get("/api/v1/health", headers={"Host": "127.0.0.1:8000"})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_frontend_favicon_is_served_without_404():
    """The production shell must serve every asset referenced by index.html."""
    response = client.get("/favicon.svg", headers={"Host": "127.0.0.1:8000"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")


def test_host_header_rejected_non_loopback():
    """Verify non-loopback Host headers (e.g. evil.com, 192.168.1.1) are rejected with 403."""
    response = client.get("/api/v1/health", headers={"Host": "evil.com"})
    assert response.status_code == 403
    assert "Non-loopback Host" in response.json()["detail"]


def test_origin_header_rejected_non_loopback():
    """Verify mutating requests with external Origin headers are rejected with 403."""
    csrf_token = security_service.generate_csrf_token()
    headers = {
        "Host": "127.0.0.1:8000",
        "Origin": "https://attacker.com",
        "X-CSRF-Token": csrf_token
    }
    response = client.post("/api/v1/session/csrf-token", headers=headers)
    assert response.status_code == 403
    assert "Non-loopback Origin" in response.json()["detail"]


def test_referer_header_rejected_non_loopback():
    """Verify mutating requests with external Referer headers are rejected with 403."""
    csrf_token = security_service.generate_csrf_token()
    headers = {
        "Host": "127.0.0.1:8000",
        "Referer": "https://malicious-site.org/phish",
        "X-CSRF-Token": csrf_token
    }
    response = client.post("/api/v1/session/csrf-token", headers=headers)
    assert response.status_code == 403
    assert "Non-loopback Referer" in response.json()["detail"]


def test_csrf_token_generation_and_validation():
    """Verify CSRF token generation and validation logic."""
    token = security_service.generate_csrf_token()
    assert security_service.validate_csrf_token(token) is True
    assert security_service.validate_csrf_token("invalid_garbage_token") is False


def test_manager_local_can_bootstrap_csrf_token(monkeypatch):
    """The local draft wizard must be able to obtain its CSRF token in manager mode."""
    monkeypatch.setenv("READ_ONLY", "True")
    monkeypatch.setenv("APP_MODE", "manager_local")
    response = client.post(
        "/api/v1/session/csrf-token",
        headers={"Host": "127.0.0.1:8000", "Origin": "http://127.0.0.1:8000"},
    )
    assert response.status_code == 200
    token = response.json()["csrf_token"]
    assert security_service.validate_csrf_token(token) is True


def test_manager_local_business_mutation_requires_csrf(monkeypatch):
    """Local capability mode must not bypass CSRF for manager decisions."""
    monkeypatch.setenv("READ_ONLY", "True")
    monkeypatch.setenv("APP_MODE", "manager_local")
    response = client.post(
        "/api/v1/records/nonexistent/notes",
        json={},
        headers={"Host": "127.0.0.1:8000", "Origin": "http://127.0.0.1:8000"},
    )
    assert response.status_code == 403
    assert "CSRF" in response.json()["detail"]


def test_manual_daily_review_requires_csrf(monkeypatch):
    """Starting a mailbox review is a privileged local mutation."""
    monkeypatch.setenv("READ_ONLY", "False")
    monkeypatch.setenv("APP_MODE", "manager_local")
    response = client.post(
        "/api/v1/daily-review/run",
        headers={"Host": "127.0.0.1:8000", "Origin": "http://127.0.0.1:8000"},
    )
    assert response.status_code == 403
    assert "CSRF" in response.json()["detail"]


def test_read_only_mode_rejects_mutations(monkeypatch):
    """Verify all mutating endpoints return 403 Forbidden when READ_ONLY=True."""
    monkeypatch.setenv("READ_ONLY", "True")
    response = client.post("/api/v1/records/syn-rec-001/notes", json={"note": "Test note"})
    assert response.status_code == 403
    assert "READ_ONLY mode is active" in response.json()["detail"]
    assert security_service.validate_csrf_token(None) is False
