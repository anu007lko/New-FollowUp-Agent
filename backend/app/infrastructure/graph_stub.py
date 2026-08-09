"""
Microsoft Graph integration adapter boundary (M1 stub).
Explicitly asserts that Mail.Send is prohibited and absent. Zero send methods or routes exist.
"""

class ProhibitedOperationError(PermissionError):
    """Raised when an illegal permission scope (such as Mail.Send) is detected."""
    pass


class GraphAdapterStub:
    """Stub representing Graph integration interface for future milestones."""

    ALLOWED_SCOPES = ["Mail.Read", "Mail.ReadWrite"]
    PROHIBITED_SCOPES = ["Mail.Send"]

    def assert_permissions_allowed(self) -> None:
        """Verify effective permissions strictly exclude Mail.Send."""
        for scope in self.PROHIBITED_SCOPES:
            if scope in self.ALLOWED_SCOPES:
                raise ProhibitedOperationError(f"Prohibited permission scope detected: {scope}")
