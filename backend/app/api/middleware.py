"""
Loopback security middleware enforcing host binding, origin/referer validation,
CORS restrictions, and CSRF token protection for mutating endpoints.
"""

import os
from urllib.parse import urlparse
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from backend.app.application.services import SecurityService
from backend.app.api.logging_config import setup_redacted_logger

logger = setup_redacted_logger("security_middleware")

ALLOWED_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "testserver"}
MUTATING_METHODS = {"POST", "PUT", "DELETE", "PATCH"}
CSRF_EXEMPT_PATHS = {
    "/api/v1/session/csrf-token", "/session/csrf-token",
    "/api/v1/imports/submissions/preview",
}
# M3 record endpoints use path-prefix matching below
# Mutating business endpoints must never be exempt by URL prefix.  The only
# exemption is the explicit session bootstrap route listed above.
CSRF_EXEMPT_PREFIXES: tuple[str, ...] = ()


class LoopbackSecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, security_service: SecurityService):
        super().__init__(app)
        self.security_service = security_service

    async def dispatch(self, request: Request, call_next):
        # 1. Host Header Check
        host_header = request.headers.get("host", "").split(":")[0].strip()
        if not host_header or host_header not in ALLOWED_LOOPBACK_HOSTS:
            logger.warning("Rejected non-loopback Host header", extra={"extra_data": {"host": host_header}})
            return JSONResponse(
                status_code=403,
                content={"detail": "Forbidden: Non-loopback Host header rejected."}
            )

        # 2. Capability Mode Check (READ_ONLY vs APP_MODE)
        if request.method in MUTATING_METHODS:
            read_only = os.environ.get("READ_ONLY", "False").lower() in ("true", "1", "yes")
            app_mode = os.environ.get("APP_MODE", "").lower()
            
            if read_only:
                if app_mode == "manager_local":
                    # In manager_local capability mode, permit ONLY the 6 local manager action endpoints
                    path = request.url.path
                    ALLOWED_LOCAL_SUFFIXES = (
                        "/notes",
                        "/follow-up-decision",
                        "/outcome-decision",
                        "/interview-confirmation",
                        "/interview-schedule",
                        "/review-deferral",
                        "/close",
                        "/reopen",
                        "/link-interview",
                        "/unlink-interview",
                    )
                    draft_suffixes = ("/draft-approve", "/draft-create", "/draft-reconcile", "/draft-resume", "/draft-reset")
                    draft_capability = (
                        os.environ.get("GRAPH_ENABLED", "False").lower() == "true"
                        and os.environ.get("DRAFTS_ENABLED", "False").lower() == "true"
                        and os.environ.get("MAIL_SEND_ENABLED", "False").lower() != "true"
                    )
                    is_csrf_bootstrap = path in CSRF_EXEMPT_PATHS and path.endswith("/session/csrf-token")
                    is_permitted_local_action = is_csrf_bootstrap or (
                        path.startswith("/api/v1/records/") and
                        (any(path.endswith(suf) for suf in ALLOWED_LOCAL_SUFFIXES)
                         or (draft_capability and any(path.endswith(suf) for suf in draft_suffixes)))
                    )
                    if not is_permitted_local_action:
                        logger.warning("Rejected non-permitted endpoint in manager_local mode", extra={"extra_data": {"path": path, "method": request.method}})
                        return JSONResponse(
                            status_code=403,
                            content={"detail": "Forbidden: Endpoint not permitted in manager_local mode."}
                        )
                else:
                    logger.warning("Rejected mutating request because READ_ONLY mode is active", extra={"extra_data": {"path": request.url.path, "method": request.method}})
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Forbidden: READ_ONLY mode is active. All database mutations and action requests are rejected."}
                    )

        # 3. Origin & Referer Validation for Mutating Requests
        if request.method in MUTATING_METHODS:
            origin = request.headers.get("origin")
            if origin:
                parsed_origin = urlparse(origin)
                hostname = parsed_origin.hostname or ""
                if hostname not in ALLOWED_LOOPBACK_HOSTS:
                    logger.warning("Rejected non-loopback Origin", extra={"extra_data": {"origin": origin}})
                    return JSONResponse(
                        status_code=403,
                        content={"detail": f"Forbidden: Non-loopback Origin '{origin}' rejected."}
                    )

            referer = request.headers.get("referer")
            if referer:
                parsed_referer = urlparse(referer)
                hostname = parsed_referer.hostname or ""
                if hostname not in ALLOWED_LOOPBACK_HOSTS:
                    logger.warning("Rejected non-loopback Referer", extra={"extra_data": {"referer": referer}})
                    return JSONResponse(
                        status_code=403,
                        content={"detail": f"Forbidden: Non-loopback Referer '{referer}' rejected."}
                    )

            # 3. CSRF Protection for Mutating Requests
            path = request.url.path
            is_draft_mutation = "/draft-" in path
            is_exempt = (not is_draft_mutation) and (path in CSRF_EXEMPT_PATHS or any(path.startswith(p) for p in CSRF_EXEMPT_PREFIXES))
            if not is_exempt:
                csrf_token = request.headers.get("x-csrf-token")
                if not self.security_service.validate_csrf_token(csrf_token):
                    logger.warning("CSRF token validation failed", extra={"extra_data": {"path": request.url.path}})
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Forbidden: Invalid or missing CSRF token."}
                    )

        response = await call_next(request)
        # Ensure security headers on responses
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';"
        return response
