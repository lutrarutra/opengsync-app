## Plan: AI support chat — floating assistant with read-only, pseudonymised tools

**TL;DR**: Add a floating chat window (available on every page) that talks to an LLM through a **Pydantic AI** agent running **inside the existing backend** as a new router. The browser sends messages via normal POSTs and receives the reply via **Server-Sent Events (SSE)**. The agent has no direct DB or file access — it can only call a small set of **read-only tools** (code search/read + focused data lookups) that run with the **logged-in user's permissions**. Everything the model sees about records is **pseudonymised** (`PROJECT_0001`, `SAMPLE_0004`, …) via a per-conversation mapping; tokens are turned back into real titles/links only when rendering HTML for the user. No MCP server is needed.

---

### Decisions
- **No MCP**: the backend *is* the client; tools are plain Python functions registered on the Pydantic AI agent. MCP may be added later as a thin wrapper over the same tool functions (e.g. for Claude Desktop with an API token via `APITokenBP`) — out of scope here
- **Runs in the backend process** (new `chat` router), not a separate container — reuses session auth, permission checks, DB blueprints and Redis. The agent module stays self-contained so it can later be split into its own compose service (same image, different command, nginx routes `/htmx/chat/` to it) without code changes
- **Transport is SSE, not WebSocket**: one POST per user message, one SSE stream per assistant reply. Cookie auth works unchanged, browser reconnect is built in, no nginx `Upgrade` handling. WebSocket only if server-initiated push is ever needed
- **Tools, not SQL**: the model never writes SQL. ~10–15 focused, read-only tools wrapping existing `opengsync_db` blueprints (`db.projects.find`, `db.projects.get_access_type`, …). No write tools in v1; future write actions must be *proposed* by the model and confirmed by the user via a UI button
- **User identity comes from deps, never from the model**: no tool takes a `user_id` argument; the user is injected through `RunContext[ChatDeps]`
- **Access checks mirror the HTML routes**: tools call the same access helpers (e.g. `get_access_type` → refuse on `AccessType.NONE`). Where possible, factor shared helpers so routes and tools can't diverge
- **Pseudonymisation (not anonymisation)**: per-conversation sequential tokens (`SAMPLE_0001`, …), *not* raw DB ids — the model can't correlate across conversations or infer record counts. Mapping (`kind → {db_id: n}`) is stored in Redis alongside the conversation history. Legally this is still personal data (GDPR) — see open questions on provider
- **Tools accept and return tokens only**: unknown/foreign tokens raise `ModelRetry`. Side effect: the model can only reference entities a tool has already shown it in this conversation (no id-guessing)
- **Tool return models are restricted types**: fields may only be `Ref` (token), enums, numbers, dates, bools. **No plain `str`** — no titles, identifiers (`project.identifier` counts as a name), sample names, person names, emails, or free-text fields (descriptions, comments, notes). Enforced by a unit test over every tool's return model
- **User input is scrubbed before every model call**: primary mechanism is an `@`-mention picker in the chat input that inserts tokens; safety net is a Pydantic AI `history_processor` that replaces names of user-accessible entities with tokens and masks emails/phone numbers by regex
- **Page context is passed as tokens** ("user is viewing EXPERIMENT_0002"), never names
- **De-pseudonymisation happens on render only**: model text (tokens) → Markdown → sanitised HTML → regex token swap → browser. Titles are `html.escape`d (user-controlled input). Stored `message_history` stays pseudonymised — only outgoing HTML contains real names
- **Titles are looked up at render time**, not stored in the mapping — renamed entities show current names, and access is re-checked (revoked → token left as-is)
- **Streaming re-renders the whole accumulated message** on each chunk (swap bubble innerHTML), which also removes the split-token-across-chunks problem. Label lookups are cached per conversation
- **Code access is allowlisted, read-only**: only `/app/services/backend/server`, `/app/packages/opengsync-db/opengsync_db` and `/templates` inside the image. Paths are resolved and checked with `Path.is_relative_to`; no config, `.env`, notebooks, `data/`, `uploads/`, `logs/`, `media/`, tests or fixtures
- **One DB session per tool call**, not the request-scoped `dependencies.db_session`: the SSE generator outlives the normal request lifecycle, and Pydantic AI runs sync tools in a thread pool (SQLAlchemy sessions are not thread-safe). Open via `app.state.db_handler.get_session()` inside each tool
- **Static context in the system prompt**: a curated summary of workflows (seq request → library → pool → experiment), status enums and checklist steps, so the model doesn't search code for basics. Cache-friendly (stable prefix)
- **Cost/abuse limits**: `dependencies.rate_limit(...)` on the message endpoint, max tool calls per turn (`UsageLimits`), max history length, stream is cancelled when the client disconnects

---

### Architecture

```
[floating chat widget (HTMX + sse ext)]
   │ POST /htmx/chat/{conv_id}/messages   → store user msg, return bubble + SSE placeholder
   │ GET  /htmx/chat/{conv_id}/stream/{id} → SSE: agent.run_stream(...), re-rendered HTML chunks
   ▼
[chat router] ── ChatDeps(user, db_handler, pseudo, redis) ──► Pydantic AI Agent ──► LLM
                                                                │
                     ┌──────────────────────────────────────────┤ tools (read-only)
                     ├─ code:  list_dir / grep_code / read_file (allowlisted paths)
                     ├─ data:  find_my_projects / get_project / find_seq_requests /
                     │         get_seq_request / get_experiment_status / list_samples / ...
                     └─ every tool: own DB session, access check, returns tokens only

Redis: chat:{user_id}:{conv_id}:history   (pseudonymised ModelMessages, TTL)
       chat:{user_id}:{conv_id}:mapping   (kind → {db_id: n}, TTL)
```

---

### Steps

#### Phase 1: Foundations

**Step 1.1** — Dependencies & config
- Add `pydantic-ai-slim[<provider>]` to `services/backend/pyproject.toml`
- Add `ChatConfig` to `AppConfig` in `server/core/config.py`: `enabled`, `model`, `base_url` (for OpenAI-compatible/self-hosted), `api_key` (env), `max_tool_calls`, `max_history_messages`, `history_ttl`, `rate_limit`
- Feature flag: router and widget only mounted/rendered when `chat.enabled`

**Step 1.2** — `server/chat/pseudonymizer.py`
- `Pseudonymizer` with `KINDS = {Project: "PROJECT", Sample: "SAMPLE", Library: "LIBRARY", SeqRequest: "REQUEST", Experiment: "EXPERIMENT", Pool: "POOL", User: "USER", ...}`
- `token(obj) -> str`, `resolve(token, expected_kind) -> int` (raises `ModelRetry` on wrong kind/unknown), `to_json()` / `from_json()` for Redis
- `TOKEN_RE = r"\b(PROJECT|SAMPLE|...)_(\d{4})\b"`

**Step 1.3** — `server/chat/refs.py`
- `Ref` type (annotated `str` produced only via `Pseudonymizer.token`)
- `ToolResult` base model + validator/test helper that rejects plain `str` fields

**Step 1.4** — `server/chat/history.py`
- Load/save `ModelMessagesTypeAdapter`-serialised history and mapping from Redis, TTL from config, truncate to `max_history_messages`

#### Phase 2: Agent & tools

**Step 2.1** — `server/chat/deps.py`
- `ChatDeps(user: models.User, db_handler, pseudo: Pseudonymizer, page_context: str | None)`
- `session()` context manager opening a fresh DB session per tool call

**Step 2.2** — `server/chat/agent.py`
- `Agent(model, deps_type=ChatDeps, instructions=...)`; instructions include: role, "refer to entities only by exact reference e.g. PROJECT_0003", "never ask for or repeat personal data", the static workflow/status summary (Step 2.5)
- Dynamic instruction adds pseudonymised page context
- `history_processors=[scrub_user_input]` (Phase 3)

**Step 2.3** — `server/chat/tools/code.py`
- `list_dir(path)`, `grep_code(pattern, path=None, max_results=50)`, `read_file(path, start=1, end=200)`
- Pure Python regex search over the allowlist (no shell), resolved-path allowlist check, line/byte caps

**Step 2.4** — `server/chat/tools/` data tools (one module per domain)
- `projects.py`: `find_my_projects(status=None, limit=20)`, `get_project(project)`
- `seq_requests.py`: `find_my_seq_requests(status=None)`, `get_seq_request(request)` incl. review/submission checklist state
- `samples.py` / `libraries.py`: `list_samples(project)`, `list_libraries(request)`, `get_library(library)`
- `experiments.py`: `get_experiment_status(experiment)` incl. checklist steps (insider-only tool, registered conditionally via `prepare`)
- Each: open session → resolve tokens → fetch → access check → build `ToolResult` with tokens → close session
- Cap all `limit`s; error messages must not contain names (use tokens)

**Step 2.5** — `server/chat/context.md` (or generated)
- Curated static summary: entity hierarchy, status enums and meaning, checklist steps. Optionally generated from enums at build time so it doesn't drift

#### Phase 3: Input scrubbing

**Step 3.1** — `server/chat/scrub.py`
- `scrub_user_input` history processor: for user-part text, replace titles/identifiers/names of entities the user can access (fuzzy, via existing `similarity` searches) with tokens (adding to mapping); regex-mask emails and phone numbers
- Optional later: Microsoft Presidio for person names in free text

**Step 3.2** — Mention picker endpoint
- `GET /htmx/chat/mentions?q=...` → returns accessible entities (projects, requests, samples) for autocomplete; selected item inserts its token into the input (token assigned server-side in the conversation mapping)

#### Phase 4: Rendering (de-pseudonymisation)

**Step 4.1** — `server/chat/render.py`
- `render_message(text, pseudo, db_handler, user, label_cache) -> Markup`
  1. Markdown → HTML (existing `markdown` dep), sanitise (allowlist tags)
  2. Collect tokens, resolve to db ids, batch-fetch titles per kind, re-check access
  3. `TOKEN_RE.sub` with callback → `<a href="{url}" class="entity-ref">{html.escape(title)}</a>`; unknown/revoked tokens left as-is
- Label cache per conversation (in-memory for the stream; optional short Redis TTL)

#### Phase 5: Routes

**Step 5.1** — `server/routes/htmx/chat.py`
- `POST /htmx/chat/new` → new `conv_id`, empty mapping/history
- `POST /htmx/chat/{conv_id}/messages` → validate ownership (`conv_id` keyed by user), store pending user message, return user bubble + assistant placeholder with `sse-connect`; `rate_limit` dependency
- `GET /htmx/chat/{conv_id}/stream/{msg_id}` → `StreamingResponse(media_type="text/event-stream")`, header `X-Accel-Buffering: no`; runs `agent.run_stream(..., message_history=..., deps=..., usage_limits=...)`, on each delta re-renders the accumulated text and emits an SSE event; stops on `request.is_disconnected()`; on completion saves pseudonymised history + mapping
- `GET /htmx/chat/{conv_id}` → re-render existing conversation (widget reopen)
- `DELETE /htmx/chat/{conv_id}` → clear history + mapping
- Register in `server/routes/htmx/__init__.py` with `require_user_id`

**Step 5.2** — nginx
- Prefer `X-Accel-Buffering: no` response header (no config change). If insufficient, add `location /htmx/chat/` with `proxy_buffering off;` and longer `proxy_read_timeout`

#### Phase 6: UI

**Step 6.1** — `templates/components/chat/widget.html`
- Floating button + collapsible panel, included from `templates/base.html` when `chat.enabled` and user logged in
- Input with `@`-mention autocomplete (Step 3.2), send via `hx-post`, stream via `htmx-ext-sse`
- Passes current page context (entity type + id) with each message; server converts to token
- Disclaimer: "Don't enter personal data. Responses may be inaccurate."

**Step 6.2** — `templates/components/chat/message.html`
- User and assistant bubbles; assistant bubble innerHTML swapped on each SSE event

#### Phase 7: Observability & audit
- Log per turn: user id, conv id, tool names called, token usage, latency (no mapping, no real names)
- Optionally record tool calls via existing `server/core/audit.py`

---

### Relevant files

**New files to create:**
- `services/backend/server/chat/__init__.py`
- `services/backend/server/chat/agent.py`
- `services/backend/server/chat/deps.py`
- `services/backend/server/chat/pseudonymizer.py`
- `services/backend/server/chat/refs.py`
- `services/backend/server/chat/history.py`
- `services/backend/server/chat/scrub.py`
- `services/backend/server/chat/render.py`
- `services/backend/server/chat/context.md`
- `services/backend/server/chat/tools/{__init__,code,projects,seq_requests,samples,libraries,experiments}.py`
- `services/backend/server/routes/htmx/chat.py`
- `services/backend/templates/components/chat/widget.html`
- `services/backend/templates/components/chat/message.html`
- `services/pytest/tests/server/chat/` (see Verification)

**Files to modify:**
- `services/backend/pyproject.toml` — add `pydantic-ai-slim[...]`
- `services/backend/server/core/config.py` — `ChatConfig`
- `services/backend/server/routes/htmx/__init__.py` — register chat router
- `services/backend/templates/base.html` — include widget
- `opengsync.yaml` (example) — `chat:` section
- `services/nginx/nginx.template.conf` — only if buffering header is not enough

**Reference files (patterns to follow):**
- `packages/opengsync-db/opengsync_db/core/blueprints/ProjectBP.py` — `find()`, `get_access_type()`
- `services/backend/server/core/dependencies.py` — `require_user`, `rate_limit`, `redis`
- `services/backend/server/core/redis.py` — `RedisClient`
- `services/backend/server/routes/htmx/projects.py` — existing access checks to mirror in tools

---

### Verification

#### Automated Tests
Use Pydantic AI's `TestModel` / `FunctionModel` — no real LLM calls in tests.

**Phase A: Pseudonymizer** (`test_chat_pseudonymizer.py`)
1. Same object → same token; different kinds numbered independently
2. `resolve` of unknown token / wrong kind raises `ModelRetry`
3. JSON round-trip preserves mapping

**Phase B: Tool safety** (`test_chat_tools.py`)
4. Every tool return model contains only `Ref`/enum/number/date/bool fields (introspection test over all registered tools)
5. `find_my_projects` returns only projects the user can access (owner, affiliation, insider, admin, deactivated)
6. `get_project` with a token for an inaccessible project → refused
7. Insider-only tools are not offered to regular users
8. Code tools reject `..`, absolute paths, symlinks out of the allowlist, and non-allowlisted dirs
9. Tool error messages contain no titles/names

**Phase C: Scrubbing** (`test_chat_scrub.py`)
10. Project title in user text → replaced with token and added to mapping
11. Title of a project the user can't access → not resolved (and not leaked)
12. Emails/phones masked

**Phase D: Rendering** (`test_chat_render.py`)
13. Tokens replaced with escaped links; title containing `<script>` is escaped
14. Title containing Markdown chars doesn't alter formatting (swap happens post-Markdown)
15. Unknown or revoked tokens left as-is
16. Stored history after a turn contains no real titles (round-trip via `FunctionModel` echoing tool output)

**Phase E: Routes** (`test_chat_routes.py`)
17. Unauthenticated → 401/redirect; other user's `conv_id` → 404
18. Message POST is rate-limited
19. SSE stream emits events with `text/event-stream` and `X-Accel-Buffering: no`
20. Chat disabled in config → routes not mounted, widget not rendered

#### Manual Verification
1. Open widget on several pages; ask "what are my projects?" → real titles shown as links in the UI
2. Inspect logged model requests → only tokens, no titles/names/emails
3. Use `@`-mention to reference a project; confirm token in stored history
4. Close the tab mid-answer → generation stops (check logs/usage)
5. Through nginx: reply streams incrementally, not all at once

---

### Open questions
1. **LLM provider**: hosted (needs GDPR DPA, EU residency, zero data retention) vs. self-hosted via OpenAI-compatible server (vLLM/Ollama)? Determines `pydantic-ai-slim` extra and whether pseudonymisation is the primary or secondary safeguard
2. **Who gets the chat**: all users, or insiders only for v1?
3. **Code tools for regular users**: should non-insiders be able to read code, or only data tools + static context?
4. **Conversation persistence**: Redis with TTL (ephemeral, e.g. 24h) vs. Postgres (history list, audit)?
5. **Which fields are acceptable to the model**: are dates, organisms, library types, sample counts OK? Are any fields (e.g. `project.identifier` like `BSF_0123`) considered non-identifying?
6. **Entity kinds in scope for v1**: projects, seq requests, samples, libraries, pools, experiments — anything else (lab preps, seq runs, files)?
