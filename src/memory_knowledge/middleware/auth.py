from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

# Paths that do not require authentication
_PUBLIC_PATHS = {"/health", "/ready", "/metrics"}


class ApiKeyAuthMiddleware(BaseHTTPMiddleware):
    """Validates Bearer token on MCP endpoints. Skips health/ready/metrics."""

    async def dispatch(self, request: Request, call_next):
        if request.url.path in _PUBLIC_PATHS:
            return await call_next(request)

        from memory_knowledge.config import get_settings

        expected = get_settings().mcp_api_key
        if expected:
            auth_header = request.headers.get("authorization", "")
            if auth_header != f"Bearer {expected}":
                return JSONResponse(
                    {"error": "Unauthorized"}, status_code=401
                )

        return await call_next(request)
