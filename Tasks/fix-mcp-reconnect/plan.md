# Plan: Fix Claude Code MCP Reconnect

## Scope

Make the remote `memory-knowledge` MCP server work with Claude Code by removing the auth middleware block on `/mcp/` paths. The MCP handshake must succeed unauthenticated because Claude Code's MCP client never sends auth headers on the initial connection probe (per MCP spec).

## Implementation Steps

### Step 1: Update auth middleware to skip `/mcp` paths

**File:** `src/memory_knowledge/middleware/auth.py`

**Change:** Add `/mcp` prefix to `_PUBLIC_PREFIXES` so all requests to `/mcp/` and sub-paths bypass the Bearer token check.

The middleware currently has:
```python
_PUBLIC_PREFIXES = ("/.well-known/",)
```

Change to:
```python
_PUBLIC_PREFIXES = ("/.well-known/", "/mcp")
```

This is the complete fix. The `/mcp` path prefix covers:
- `POST /mcp/` — MCP initialize, tool calls
- `GET /mcp/` — SSE stream (if used)  
- `DELETE /mcp/` — session termination

### Step 2: Remove debug logging

Remove the `AUTH_DEBUG` logging added during investigation (logger import, warning call in dispatch method). Revert to clean middleware.

### Step 3: Clean up unnecessary discovery routes

**File:** `src/memory_knowledge/server.py`

The `/.well-known/openid-configuration`, `/.well-known/oauth-protected-resource`, `/.well-known/oauth-protected-resource/{path:path}`, and `/register` routes added during investigation are no longer needed — they were meant to handle the OAuth discovery flow, but since `/mcp/` no longer returns 401, Claude Code won't trigger OAuth discovery at all.

Keep only `/.well-known/oauth-authorization-server` as a defensive measure in case any client probes it.

Actually — keep all of them. They're harmless 404s and serve as documentation of the protocol flow. Zero cost, defensive benefit.

### Step 4: Revert settings.json type change

**File:** `~/.claude/settings.json`

Change `type: "http"` back to `type: "url"` for `memory-knowledge` — the type doesn't matter since auth bypass is server-side now. But actually, either works. Leave as `type: "http"` since that's the documented type.

### Step 5: Deploy

1. Commit changes
2. `az acr build` to build in ACR
3. `az webapp restart` to deploy
4. Verify with `claude mcp list` and `/mcp`

## Affected Files

- `src/memory_knowledge/middleware/auth.py` — add `/mcp` to public prefixes, remove debug logging
- `~/.claude/settings.json` — already updated (keep as-is)

## Security Considerations

The MCP endpoint becomes publicly accessible without auth. Risk assessment:
- **Tool schemas**: Exposed but not sensitive (tool names and parameter schemas)
- **Tool execution**: Returns actual data — this is the sensitive part
- **Mitigation**: The URL is not publicly documented. For stronger auth, implement MCP-spec OAuth later.

## Validation

1. `curl -s -X POST https://memory-knowledge.azurewebsites.net/mcp/ -H "Content-Type: application/json" -H "Accept: application/json" -d '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}},"id":1}'` → should return 200 (no auth needed)
2. `claude mcp list` → should show `memory-knowledge: ✓ Connected`
3. `/mcp` in Claude Code → should succeed
