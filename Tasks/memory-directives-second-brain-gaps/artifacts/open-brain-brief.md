# Open Brain (OB1) & Open Skills — Research Brief

**Prepared:** 2026-06-20 · **Author of the system:** Nate B. Jones · **Scope:** What it is, the principles & architecture that drive it, and the best way to use it.
**Method:** Grounded in the local repo checkout (`/Users/kamenkamenov/Downloads/OB1-main`) for all schema/code claims, plus deep external research across Nate B. Jones' own writing and the official repo (25/25 verified claims, 0 refuted). Table, column, and tool names are taken verbatim from the repo — none are invented.

---

## 1. TL;DR

Open Brain ("OB1") is an **open-source persistent-memory layer for AI**. Instead of every AI app (Claude, ChatGPT, Cursor, Gemini, Grok) keeping its own siloed, forgettable memory, OB1 gives you **one database you own** that **any MCP-capable AI client can read from and write to**. You capture "thoughts" from whatever tool you're in; they're embedded, classified, and stored once; and every other AI can later retrieve them by meaning.

The whole system is deliberately small: **one Postgres database (Supabase + pgvector), one MCP server (a single Supabase Edge Function), one access key, any AI client.** Setup is ~30 minutes, no coding, on two services (Supabase free tier + ~$5 of OpenRouter credits).

**Open Skills** is Jones' newer companion project: a library of **reusable AI-agent "primitives" — compact operating procedures an agent loads on demand**. The pairing has a single thesis: *Open Brain keeps your **memory** yours; Open Skills keeps your **way of working** yours* — neither rented back to you by whichever AI vendor wins this month.

---

## 2. What It Is — and Who It's For

### The problem it attacks
Every AI chat "starts from zero." Memory features exist (ChatGPT Memory, Claude projects, etc.), but each is **locked inside one vendor**. Switch tools — or use several at once — and the context doesn't follow you. OB1's framing: *"Your second brain is closed. Your AI can't use it. Here's the fix."*

### The product, in one line
> "This isn't a notes app. It's a database with vector search and an open protocol — built so that every AI tool you use shares the same persistent memory of you." — repo `README.md`

OB1 is **infrastructure, not an app**. There is no OB1 UI you live in. The "interface" is whatever AI you already use; OB1 is the shared backend behind all of them. Explicitly *not* an Obsidian/Notion replacement — those are document-authoring frontends; OB1 is a retrieval-by-meaning memory layer. (The FAQ is blunt that the two solve different problems and can coexist.)

### Who it's for
- **Anyone who uses more than one AI tool** and is tired of re-explaining themselves. The stated design goal is **zero switching cost across clients**.
- **Non-engineers** — the canonical setup requires no coding ("Zero coding experience").
- **Builders/tinkerers** — a curated learning path and an open contribution ecosystem (recipes, schemas, integrations, skills) let you extend it as far as you want, including full self-hosting on Kubernetes.

### Provenance & license
- Official repo: **`github.com/NateBJones-Projects/OB1`**, created by Nate B. Jones; released ~March 2026.
- License: **FSL-1.1-MIT** (Functional Source License). Practical implication: **no commercial derivative works** — fine for personal/internal use and community contribution, but a constraint to check before building a commercial product on top of it.
- Maintained by Nate B. Jones with a small repo team (Jonathan Edwards – repo manager; Matt Hallett – community admin; Alan Shurafa – community maintainer). PRs pass an automated review gate, then human review.

---

## 3. Principles That Drive It

These are the design values that explain almost every architectural choice:

1. **You own the data outright.** It lives in *your* Supabase project (or your own Postgres/K8s). No middleware, no SaaS chain, no Zapier. The repo phrase: *"one database, one AI gateway, one chat channel."*
2. **Open protocol over integrations.** MCP (Model Context Protocol) is the single contract. Any client that speaks MCP plugs in with **one URL** — no per-tool connectors to maintain.
3. **Portability / vendor-neutrality.** "Whatever ships next month" should just work. The model gateway (OpenRouter) and the protocol (MCP) are both chosen specifically so no single AI vendor is load-bearing.
4. **Retrieval by meaning, not filing.** You don't organize thoughts into folders. You capture; vector search retrieves what's relevant. "You're not the librarian anymore."
5. **Radical simplicity at the core, extensibility at the edges.** The core is one table + a handful of tools. Everything else (extensions, recipes, schemas) is **additive** and optional.
6. **Don't break the core.** A hard guard rail (`CLAUDE.md`): *never modify the core `thoughts` table structure* — adding columns/sidecar tables is fine; altering or dropping existing ones is not. This keeps every extension compatible.
7. **Remote, not local.** MCP servers are **Supabase Edge Functions**, never local Node processes or `claude_desktop_config.json` stdio servers. This is what makes "any client, one URL" work.
8. **AI-assisted everything.** You're encouraged to build/extend OB1 *using* AI (the Supabase AI assistant, plus dedicated companion assistants). "You just built AI infrastructure using AI."

---

## 4. Architecture

### 4.1 The shape

```
   Claude Desktop ─┐
   ChatGPT ────────┤        ┌─────────────────────────────┐
   Claude Code ────┼──MCP──▶ │  Supabase Edge Function     │
   Cursor / Codex ─┤  (one   │  "open-brain-mcp"  (the     │
   Gemini / Grok ──┘   URL)  │   remote MCP server)        │
                             │   ├─ embeds via OpenRouter   │
                             │   ├─ extracts metadata (LLM) │
                             │   └─ reads/writes Postgres   │
                             └──────────────┬──────────────┘
                                            ▼
                             ┌─────────────────────────────┐
                             │ Supabase Postgres + pgvector │
                             │   table: thoughts            │
                             │   fn: match_thoughts         │
                             │   fn: upsert_thought         │
                             └─────────────────────────────┘
```

Two external services only: **Supabase** (database, free tier) and **OpenRouter** (AI gateway, ~$5 credits lasts months). OpenRouter is chosen over calling OpenAI directly so you can later swap embedding/LLM models — or move to Claude/Gemini — with one config change.

### 4.2 The data model — the `thoughts` table

Verified verbatim from `docs/01-getting-started.md`. The base `CREATE TABLE` has six columns; `content_fingerprint` is added afterward via `ALTER TABLE` for dedup:

| Column | Type | Purpose |
|---|---|---|
| `id` | `uuid` (PK, `gen_random_uuid()`) | Stable identifier |
| `content` | `text not null` | The raw thought |
| `embedding` | `vector(1536)` | Semantic vector (pgvector) |
| `metadata` | `jsonb` (default `{}`) | LLM-extracted structure (see below) |
| `content_fingerprint` | `text` (added later) | SHA-256 of normalized content for dedup |
| `created_at` | `timestamptz` | Capture time |
| `updated_at` | `timestamptz` | Auto-updated via trigger |

Supporting database objects (also verbatim from the setup guide):
- **Indexes:** HNSW index on `embedding` (`vector_cosine_ops`) for fast similarity; GIN index on `metadata` for structured filters; a `created_at desc` index for recency; a **unique** partial index on `content_fingerprint` for dedup.
- **`match_thoughts(query_embedding, match_threshold, match_count, filter)`** — the semantic search RPC. Returns rows where cosine similarity > threshold, optionally filtered by `metadata @> filter`, ordered by distance. (Default threshold 0.7 in SQL; the server calls it at 0.5.)
- **`upsert_thought(p_content, p_payload)`** — inserts a new thought or, on fingerprint collision, **merges metadata** instead of creating a duplicate row.
- **Security:** Row Level Security is enabled; a `service_role` full-access policy plus an explicit `GRANT` (newer Supabase projects don't grant table CRUD to `service_role` by default — a documented gotcha).

The **`metadata` jsonb** is where structure lives without schema changes. The capture LLM extracts: `people[]`, `action_items[]`, `dates_mentioned[]` (YYYY-MM-DD), `topics[]` (1–3 tags), and `type` (one of `observation`, `task`, `idea`, `reference`, `person_note`). Captures from the MCP path are tagged `source: "mcp"`.

### 4.3 The MCP server (`server/index.ts`)

A single Deno Edge Function (Hono + the MCP SDK over `StreamableHTTPTransport`). It registers **four core tools** plus **two ChatGPT-compatibility aliases** (six total):

| Tool | Read/Write | What it does |
|---|---|---|
| `search_thoughts` | read | Semantic search (`query`, optional `limit`, `threshold`) via `match_thoughts` |
| `list_thoughts` | read | Browse recent, filterable by `type` / `topic` / `person` / `days` |
| `thought_stats` | read | Totals, type breakdown, top topics, most-mentioned people |
| `capture_thought` | write (bounded, non-destructive) | Embed + extract metadata **in parallel**, then `upsert_thought` |
| `search` *(alias)* | read | ChatGPT-shaped search returning `{id,title,url}` results |
| `fetch` *(alias)* | read | ChatGPT-shaped fetch of one thought by `id` for citation |

Implementation details worth knowing:
- **Embeddings:** `openai/text-embedding-3-small` via OpenRouter (1536 dims — must match the column). **Metadata extraction:** `openai/gpt-4o-mini` with JSON-object response format. Swap either by editing the model strings and redeploying (keep dims at 1536).
- **Auth:** a single shared access key checked on every request, accepted **either** as header `x-brain-key` **or** as `?key=` in the URL. (Claude Desktop/ChatGPT can't send custom headers → use the `?key=` URL; Claude Code can → use the header. This header-vs-query split is "the single most common issue.")
- **Robustness fixes baked in:** auth failures return a **JSON-RPC error envelope (HTTP 200)** rather than a bare 401, because strict MCP hosts (Codex, Claude Code) tear down the connection on transport 4xx. It also patches a missing `Accept: text/event-stream` header that Claude Desktop connectors omit. CORS is wide-open by design for browser/Electron clients.
- **Read-only hints** are set so ChatGPT (which treats unhinted tools as write actions) exposes the read tools even on restricted plans.

### 4.4 Repo structure (the extension surface)

```
extensions/   — curated, ordered learning path (6 builds; maintainer-gated)
primitives/   — reusable concept guides (deploy-edge-function, remote-mcp, rls,
                shared-mcp, troubleshooting) reused by ≥2 extensions
recipes/      — standalone capability builds & data importers (open to community)
schemas/      — additive table/sidecar extensions (e.g. agent-memory, entity-extraction)
dashboards/   — Vercel/Netlify frontends pointed at your Supabase
integrations/ — capture sources (Slack, Discord, Telegram…), alt deploys (K8s),
                MCP extensions, Agent Memory API
skills/       — installable AI-client skill packs (SKILL.md prompt packs)
docs/         — getting-started, companion prompts, FAQ, AI-assisted setup
```

Two notable advanced layers in the repo:
- **Agent Memory** (`schemas/agent-memory`, `integrations/agent-memory-api`): provenance, review, use-policy, source-reference, relation, recall-trace, and audit *sidecars* for agent-workflow memory — a governed continuity layer (flagship runtime: OpenClaw). Principle: *inferred/generated memory is "evidence" by default; instruction-grade memory needs human confirmation.*
- **Knowledge-graph recipes** (entity extraction, typed reasoning edges, entity wiki, wiki synthesis) that build a graph/wiki on top of the flat thoughts store.

---

## 5. Open Skills — the Complement

**What it is (external, primary source `unlock-ai.natebjones.com/open-skills`):**
> "Open Skills is a library of reusable AI-agent primitives: compact operating procedures your agent loads on demand."

Where Open Brain supplies the *context* (your accumulated memory), Open Skills supplies the *repeatable way of working* — packaged procedures an agent invokes when a task matches. Jones' positioning makes the pairing explicit:
> "Open Brain kept your memory yours. Open Skills keeps the way you work yours, not rented back by whichever AI app wins this month." (natebjones.com, Jun 2026)
> "OpenBrain gives agents the context; OpenSkills gives them the repeatable way to work."

Companion materials reference roughly **"31 skills, 7 runbooks."** It's published under Jones' **"Unlock AI"** brand.

**How it shows up in this repo.** The OB1 repo already ships a `skills/` directory that embodies the same idea — plain-text, installable **skill packs** with a Claude-skill-style format: YAML frontmatter (`name`, `description`, `author`, `version`) plus markdown sections (`Problem`, `When to Use` / `Trigger Conditions`, `Process`, `Output`). Examples shipped: `research-synthesis`, `competitive-analysis`, `deal-memo-drafting`, `financial-model-review`, `meeting-synthesis`, `panning-for-gold`, `auto-capture`, `work-operating-model`, `world-model-diagnostic`. Many can optionally **read from and capture to Open Brain**, closing the loop: a skill pulls prior context from your brain, runs a procedure, and writes the result back.

> Note: "Open Skills" as a standalone library (the 31-skills/7-runbooks product on Unlock AI) and the OB1 repo's `skills/` folder are the same idea expressed in two places. Treat the repo's `skills/` as the in-tree, OB1-integrated subset; the Unlock AI page is the broader library and positioning.

---

## 6. The Best Way to Use It

### 6.1 Stand up the core (~30 min, no coding)
Follow `docs/01-getting-started.md` (or the ~27-min video). The 8 steps:
1. **Create a Supabase project** — save the Project ref + DB password.
2. **Build the database** — enable pgvector, then run the SQL for the `thoughts` table + indexes, `match_thoughts`, RLS policy, the `service_role` `GRANT` (don't skip — causes "permission denied"), and the dedup fingerprint + `upsert_thought`.
3. **Save connection details** — Project URL + Secret key.
4. **Get an OpenRouter key** — add ~$5 credits.
5. **Create one access key** — `openssl rand -hex 32`. This is your *single* key for the core and every future extension. Store it permanently.
6. **Deploy the MCP server** — `supabase functions deploy open-brain-mcp --no-verify-jwt`; set secrets `MCP_ACCESS_KEY` and `OPENROUTER_API_KEY`.
7. **Connect your AI client(s):**
   - **Claude Desktop:** Settings → Connectors → Add custom connector → paste the `…/open-brain-mcp?key=YOUR_KEY` URL. No JSON, no terminal.
   - **Claude Code:** `claude mcp add --transport http open-brain <url> --header "x-brain-key: YOUR_KEY"`.
   - **ChatGPT (paid + Developer Mode):** Apps & Connectors → Create → paste the `?key=` URL, auth "None". (Enabling Dev Mode disables ChatGPT's built-in memory — OB1 replaces it.)
   - **Codex / Cursor / others:** bridge with `mcp-remote` or `supergateway`; set a generous startup timeout.
8. **Use it** — capture a test thought, then search for it. Confirm a row appears in Supabase.

> **Tip from the FAQ:** when something breaks, it's almost always *configuration* (mismatched key, missing `?key=`, skipped GRANT), **not** the code. Check Supabase → Edge Functions → Logs first. Don't let an AI rewrite the working server.

### 6.2 Fill the brain & build the habit (the 5-prompt lifecycle)
From `docs/02-companion-prompts.md`, run in order:
1. **Memory Migration** — extract what your current AI already knows about you and capture it, so every tool starts with context.
2. **Second Brain Migration** — bulk-import Notion/Obsidian/Apple Notes/text.
3. **Open Brain Spark** — personalized use-case discovery from *your* workflow.
4. **Quick Capture Templates** — five sentence patterns that produce clean metadata.
5. **The Weekly Review** — a Friday ritual surfacing themes, forgotten action items, and connections.

For bulk/real data, use **recipes** (Gmail, ChatGPT export, X/Twitter, Obsidian vault, Google Takeout, etc.). Add **capture sources** (Slack/Discord/Telegram) if you want quick-capture outside your AI tools.

### 6.3 Then extend — pick from the learning path
Run the **Extension Matchmaker** prompt (it interviews you and recommends a build order), then work the curated 6-extension path, which compounds: **Household Knowledge → Home Maintenance → Family Calendar → Meal Planning → Professional CRM → Job Hunt Pipeline.** Each extension reuses **primitives** (deploy-edge-function, remote-mcp, RLS, shared-mcp) and is **additive** to the core. Beyond that, browse community **recipes / schemas / dashboards / integrations / skills**.

### 6.4 Layer in Open Skills
Drop relevant **skill packs** into your AI client (Claude Code, Codex, Claude Desktop) so recurring work (research synthesis, meeting notes → actions, competitive briefs, idea mining) runs as a consistent procedure that reads/writes your brain. For agent workflows that need governed, auditable memory, look at the **Agent Memory** schema + API.

### 6.5 Operating best practices (drawn from the docs/FAQ)
- **Capture atomically.** Short, standalone, single-idea thoughts embed tightest and retrieve best. For long documents, **chunk** them (parent doc + chunks table) rather than embedding a 4,000-word blob as one vector — hybrid filter (metadata) + vector search inside the filtered set.
- **Trust the embedding, not the tags.** Metadata extraction is best-effort; semantic search works regardless. Use capture templates if you need consistent classification.
- **Widen search when empty.** Ask for a lower threshold (e.g., 0.3) to cast a wider net.
- **Treat the access key like a password**; rotate by re-running `supabase secrets set` (rotating it on OpenRouter alone won't propagate).
- **Don't alter the core table.** Add columns/sidecars; never drop/change existing ones (keeps extensions compatible).
- **Self-host option:** for full control, the K8s integration runs Postgres + pgvector with no Supabase.

---

## 7. Caveats & Things to Verify

These are honest limits surfaced by the research (mostly because the sources are largely the author's own):
- **"Two *free* services" is imprecise.** Supabase has a real free tier; **OpenRouter needs ~$5 paid credits.** Running cost is famously low (~$0.10/month claimed) but not zero.
- **Minor doc inconsistency on setup time:** README says ~45 min; the getting-started guide and promptkit say ~30 min.
- **"One MCP server" describes the core.** Each *extension* deploys as its own Edge Function, so a fully extended install exposes multiple MCP endpoints.
- **"Any AI client" requires remote-MCP support.** ChatGPT needs a paid Developer-Mode tier; stdio-only clients need an `mcp-remote`/`supergateway` bridge. Client MCP support is evolving fast (e.g., Grok native MCP landed May 2026) — verify current state for your tool.
- **Little independent validation.** Most evidence is Jones' own primary writing + the official repo (authoritative for *what it is*, less so for benchmarked real-world retrieval quality at scale). No third-party eval of retrieval accuracy was found.
- **License constraint:** FSL-1.1-MIT forbids commercial derivative works — check before building a commercial product on it.

---

## 8. Sources

**Internal (verified directly in `/Users/kamenkamenov/Downloads/OB1-main`):** `README.md`, `docs/01-getting-started.md`, `docs/02-companion-prompts.md`, `docs/03-faq.md`, `server/index.ts`, `skills/README.md` & `skills/*/SKILL.md`, `AGENTS.md`, `CLAUDE.md`, repo tree (`extensions/`, `primitives/`, `recipes/`, `schemas/`, `integrations/`).

**External (deep-research, 25/25 claims confirmed, 0 refuted):**
- Nate's Newsletter / Substack: *"Every AI You Use Forgets You — Here's the Fix"* — `natesnewsletter.substack.com/p/every-ai-you-use-forgets-you-heres`; note `c-223200688`.
- Official repo: `github.com/NateBJones-Projects/OB1` (incl. `docs/01-getting-started.md`, `docs/02-companion-prompts.md`).
- Promptkit: `promptkit.natebjones.com/20260224_uq1_guide_main`, `/20260305_395_promptkit_substack_1`.
- Open Skills: `unlock-ai.natebjones.com/open-skills`; `natebjones.com`.
- LinkedIn launch post (Nate B. Jones, "Introducing Open Brain").
- Secondary/explanatory: `mindstudio.ai` blog, `simplenews.ai`, Medium technical walkthrough.
