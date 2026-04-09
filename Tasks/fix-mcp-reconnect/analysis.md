# Analysis: Fix Claude Code MCP Reconnect to Remote Server

## Task Objective

Fix the remote `memory-knowledge` MCP server so that Claude Code can connect using static Bearer token auth configured in settings.json.

## Confirmed Root Cause

### Evidence: Server Logs with Debug Header Logging

Multiple `/mcp` reconnect attempts captured the exact request sequence:

```
POST /mcp/ HTTP/1.1  → 401 Unauthorized   (NO authorization header present)
GET /.well-known/oauth-authorization-server → 404
GET /.well-known/openid-configuration → 404
GET /.well-known/oauth-protected-resource/mcp → 404
GET /.well-known/oauth-protected-resource → 404
POST /register → 404
→ Client gives up: "Failed to reconnect"
```

Debug header logging confirmed the initial `POST /mcp/` has **no Authorization header at all**. The `headers` field in settings.json is NOT applied to the initial MCP connection probe.

### Why This Happens: MCP Protocol Design

The MCP spec (2025-03-26) mandates:
1. Client sends initial request to MCP endpoint **without auth**
2. If server returns 401, client **MUST** attempt OAuth 2.1 discovery per RFC 9728
3. If OAuth discovery fails → client gives up

Claude Code follows this spec. The static `headers` from settings.json are NOT sent on the initial probe. They may only be used after OAuth discovery succeeds (or possibly never for the auth-required case).

### What We've Tried and Ruled Out

1. **`type: "url"` → `type: "http"` in settings.json**: No effect — same behavior
2. **Making `/.well-known/*` and `/register` return 404 instead of 401**: Correct but insufficient — the core issue is the initial 401 on `POST /mcp/`
3. **FastMCP built-in auth**: Requires implementing a full `OAuthAuthorizationServerProvider` — massive overkill for static Bearer tokens

### Why Local Server Works

`memory-knowledge-local` (localhost:8000) has no `MCP_API_KEY` set. The middleware's `if expected:` check passes through — first POST succeeds unauthenticated, MCP handshake completes, Claude Code connects.

## Constraints

1. Server is publicly accessible — we need some form of auth
2. Cannot modify Claude Code's MCP client
3. MCP spec requires 401 → OAuth, no "static Bearer" mode
4. Local server must continue working without auth
5. Implementing full OAuth server is disproportionate to the problem

## Recommended Approach

**Bypass auth middleware for `/mcp/` paths. Check Bearer token inside MCP tool handlers.**

This means:
- MCP handshake (`initialize`, `initialized`) succeeds unauthenticated — this is harmless, it only exchanges protocol capabilities
- Tool calls (`tools/call`) check the Bearer token — this is where actual data access happens
- The middleware continues to protect any future non-MCP endpoints

The security model shifts from "block at the door" to "check credentials at the vault." The MCP handshake leaks nothing sensitive — it only returns server capabilities and tool definitions.

## Source Artifacts Inspected

- `src/memory_knowledge/middleware/auth.py` — custom auth middleware
- `src/memory_knowledge/server.py` (lines 50-56, 1035-1059) — FastMCP config and Starlette app
- `.venv/lib/python3.14/site-packages/mcp/server/fastmcp/server.py` (lines 950-1045) — FastMCP streamable HTTP setup
- `.venv/lib/python3.14/site-packages/mcp/server/auth/provider.py` — TokenVerifier protocol
- `.venv/lib/python3.14/site-packages/mcp/server/auth/middleware/bearer_auth.py` — RequireAuthMiddleware
- `.venv/lib/python3.14/site-packages/mcp/server/auth/settings.py` — AuthSettings model
- `.venv/lib/python3.14/site-packages/mcp/server/auth/routes.py` — OAuth route creation
- `~/.claude/settings.json` — MCP server configuration
- Azure Web App logs — request headers during failed reconnect
- MCP spec (2025-03-26) transports and authorization sections
