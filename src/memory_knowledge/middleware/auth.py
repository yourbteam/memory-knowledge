from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

# Paths that do not require authentication
_PUBLIC_PATHS = {"/health", "/ready", "/metrics", "/register"}

# Prefixes that bypass auth.
# - /.well-known/  → OAuth/OIDC discovery (RFC 9728)
# - /mcp           → MCP streamable-HTTP endpoint; must be unauthenticated
#                    because the MCP spec requires the client to probe without
#                    auth first and attempt OAuth discovery on 401.  Claude Code
#                    never sends static Bearer headers on the initial request.
_PUBLIC_PREFIXES = ("/.well-known/", "/mcp")


class ApiKeyAuthMiddleware(BaseHTTPMiddleware):
    """Validates Bearer token on non-MCP endpoints. MCP auth is open (see above)."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in _PUBLIC_PATHS or path.startswith(_PUBLIC_PREFIXES):
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
