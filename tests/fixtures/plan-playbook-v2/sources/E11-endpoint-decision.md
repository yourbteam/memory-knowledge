### 0.1 Canonical brain endpoint — **DECIDED: Azure (Kamen, 2026-06-20)**
**Practical problem (resolved).** Three consumers read the brain through **two** different endpoints, so they can return different results for the same query:
- Claude Code MCP tools → `http://localhost:8000/mcp/` (`~/.claude/settings.json` → `memory-knowledge-local`).
- Claude Code corpus hook → Azure (`hydrate_corpus.py` default `CLAUDE_CORPUS_MCP_URL`).
- Codex MCP → Azure (`~/.codex/config.toml` → `mcp_servers.memory-knowledge`).

**Decision:** **Azure (`https://memory-knowledge.azurewebsites.net/mcp/`) is canonical** for all three consumers, set via a single env var with one default; **localhost `:8000` is an opt-in dev override** (set the env var locally when doing server dev). Rationale: matches the cross-tool/cross-machine portability thesis and is already the default for 2 of 3 consumers; offline degradation is already fail-open. **Implication for §5 (X-DEPLOY):** the `corpus_query` recency change must be deployed to the Azure server to take effect for all consumers.
