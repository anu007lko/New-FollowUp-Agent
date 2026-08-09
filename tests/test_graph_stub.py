"""
Automated negative test proving zero send surface exists and Mail.Send is prohibited.
"""

import inspect
import pytest
from backend.app.infrastructure.graph_stub import GraphAdapterStub, ProhibitedOperationError
from backend.app.main import app


def test_no_send_methods_or_attributes():
    """Statically assert that no send methods or callables exist on GraphAdapterStub."""
    stub = GraphAdapterStub()

    # Assert no method or property contains 'send'
    members = dict(inspect.getmembers(stub))
    send_members = [name for name in members if "send" in name.lower() and name != "PROHIBITED_SCOPES"]

    assert len(send_members) == 0, f"Found unexpected send method/attribute: {send_members}"
    assert not hasattr(stub, "send_mail")
    assert not hasattr(stub, "send")


def test_no_send_routes_in_fastapi():
    """Statically assert that no FastAPI route path contains 'send'."""
    routes = []
    for route in app.routes:
        path = getattr(route, "path", None)
        if path:
            routes.append(path)

    send_routes = [p for p in routes if "send" in p.lower()]
    assert len(send_routes) == 0, f"Found unexpected send route in FastAPI app: {send_routes}"


def test_graph_permissions_assert_no_send():
    """Verify permissions assertion succeeds and Mail.Send is absent."""
    stub = GraphAdapterStub()
    stub.assert_permissions_allowed()
    assert "Mail.Send" not in stub.ALLOWED_SCOPES
    assert "Mail.Send" in stub.PROHIBITED_SCOPES
