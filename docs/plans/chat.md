## Plan: AI support chat — floating assistant with read-only, pseudonymised tools

**TL;DR**: Add a floating chat window (available on every page) that talks to an LLM through a **Pydantic AI** agent running **inside the existing backend** as a new router. The browser sends messages via normal POSTs and receives the reply via **Server-Sent Events (SSE)**. The agent has no direct DB or file access — it can only call a small set of **read-only tools** (code search/read + focused data lookups) that run with the **logged-in user's permissions**. Everything the model sees about records is **pseudonymised** (`PROJECT_0001`, `SAMPLE_0004`, …) via a per-user mapping; tokens are turned back into real titles/links only when rendering HTML for the user. No MCP server is needed. Each user has a **single conversation**, stored in Redis under their user id and kept for **24 hours**.

---

### Decisions
- **No MCP**: the backend *is* the client; tools are plain Python functions registered on the Pydantic AI agent. MCP may be added later as a thin wrapper over the same tool functions (e.g. for Claude Desktop with an API token via `APITokenBP`) — out of scope here
- **Runs in the backend process** (new `chat` router), not a separate container — reuses session auth, permission checks, DB blueprints and Redis. The agent module stays self-contained so it can later be split into its own compose service (same image, different command, nginx routes `/htmx/chat/` to it) without code changes
- **Transport is SSE, not WebSocket**: one POST per user message, one SSE stream per assistant reply. Cookie auth works unchanged, browser reconnect is built in, no nginx `Upgrade` handling. WebSocket only if server-initiated push is ever needed
- **Tools, not SQL**: the model never writes SQL. ~10–15 focused, read-only tools wrapping existing `opengsync_db` blueprints (`db.projects.find`, `db.projects.get_access_type`, …). No write tools in v1; future write actions must be *proposed* by the model and confirmed by the user via a UI button
- **User identity comes from deps, never from the model**: no tool takes a `user_id` argument; the user is injected through `RunContext[ChatDeps]`
- **Access checks mirror the HTML routes**: tools call the same access helpers (e.g. `get_access_type` → refuse on `AccessType.NONE`). Where possible, factor shared helpers so routes and tools can't diverge
- **Single conversation per user**: no conversation ids, no "new conversation" action. History and mapping are keyed by user id and share a 24h TTL (refreshed on each message), so the conversation effectively resets after 24h of inactivity
- **Pseudonymisation (not anonymisation)**: per-user sequential tokens (`SAMPLE_0001`, …), *not* raw DB ids — the model can't infer record counts. Mapping (`kind → {db_id: n}`) is stored in Redis alongside the conversation history and expires with it, so numbering restarts with each new conversation. Legally this is still personal data (GDPR) — see open questions on provider
- **Tools accept and return tokens only**: unknown/foreign tokens raise `ModelRetry`. Side effect: the model can only reference entities a tool has already shown it in this conversation (no id-guessing)
- **Tool return models are restricted types**: fields may only be `Ref` (token), enums, numbers, dates, bools. **No plain `str`** — no titles, identifiers (`project.identifier` counts as a name), sample names, person names, emails, or free-text fields (descriptions, comments, notes). Enforced by a unit test over every tool's return model
- **User input is scrubbed before every model call**: a Pydantic AI `history_processor` replaces names of user-accessible entities with tokens and masks emails/phone numbers by regex. An `@`-mention picker that inserts tokens directly is deferred (see Later)
- **Page context is passed as tokens** ("user is viewing EXPERIMENT_0002"), never names
- **De-pseudonymisation happens on render only**: model text (tokens) → Markdown → sanitised HTML → regex token swap → browser. Titles are `html.escape`d (user-controlled input). Stored `message_history` stays pseudonymised — only outgoing HTML contains real names
- **Titles are looked up at render time**, not stored in the mapping — renamed entities show current names, and access is re-checked (revoked → token left as-is)
- **Streaming re-renders the whole accumulated message** on each chunk (swap bubble innerHTML), which also removes the split-token-across-chunks problem. Label lookups are cached per stream
- **Code access is allowlisted, read-only**: only `/app/services/backend/server`, `/app/packages/opengsync-db/opengsync_db` and `/templates` inside the image. Paths are resolved and checked with `Path.is_relative_to`; no config, `.env`, notebooks, `data/`, `uploads/`, `logs/`, `media/`, tests or fixtures
- **One DB session per tool call**, not the request-scoped `dependencies.db_session`: the SSE generator outlives the normal request lifecycle, and Pydantic AI runs sync tools in a thread pool (SQLAlchemy sessions are not thread-safe). Open via `app.state.db_handler.get_session()` inside each tool
- **Static context in the system prompt**: a curated summary of workflows (seq request → library → pool → experiment), status enums and checklist steps, so the model doesn't search code for basics. Cache-friendly (stable prefix)
- **Cost/abuse limits**: `dependencies.rate_limit(...)` on the message endpoint, max tool calls per turn (`UsageLimits`), max history length, stream is cancelled when the client disconnects

---

### Architecture

```
[floating chat widget (HTMX + sse ext)]
   │ GET  /htmx/chat                 → render the user's conversation
   │ POST /htmx/chat/messages        → store user msg, return bubble + SSE placeholder
   │ GET  /htmx/chat/stream/{msg_id} → SSE: agent.run_stream(...), re-rendered HTML chunks
   ▼
[chat router] ── ChatDeps(user, db_handler, pseudo, redis) ──► Pydantic AI Agent ──► LLM
                                                                │
                     ┌──────────────────────────────────────────┤ tools (read-only)
                     ├─ code:  list_dir / grep_code / read_file (allowlisted paths)
                     ├─ data:  find_my_projects / get_project / find_seq_requests /
                     │         get_seq_request / get_experiment_status / list_samples / ...
                     └─ every tool: own DB session, access check, returns tokens only

Redis: chat:{user_id}:history   (pseudonymised ModelMessages, 24h TTL)
       chat:{user_id}:mapping   (kind → {db_id: n}, 24h TTL)
       chat:{user_id}:messages  (display list: msg_id, user text, status; 24h TTL)
```

---

### Steps

#### Phase 1: Foundations

**Step 1.1** — Dependencies & config ✅
- Done: `pydantic-ai-slim[openai,anthropic]`; `ChatConfig` (`enabled`, `model` — `"test"` = offline echo model, `base_url`, `history_ttl_hours`, `max_history_turns`, `max_requests_per_turn`) under `chat:` in `opengsync.yaml`; `CHAT_API_KEY` env for `base_url`; `chat_enabled` template global; routes return 404 when disabled
- Add `pydantic-ai-slim[<provider>]` to `services/backend/pyproject.toml`
- Add `ChatConfig` to `AppConfig` in `server/core/config.py`: `enabled`, `model`, `base_url` (for OpenAI-compatible/self-hosted), `api_key` (env), `max_tool_calls`, `max_history_messages`, `history_ttl` (default 24h), `rate_limit`
- Feature flag: router and widget only mounted/rendered when `chat.enabled`

**Step 1.2** — `server/chat/pseudonymizer.py`
- `Pseudonymizer` with `KINDS = {Project: "PROJECT", Sample: "SAMPLE", Library: "LIBRARY", SeqRequest: "REQUEST", Experiment: "EXPERIMENT", Pool: "POOL", User: "USER", ...}`
- `token(obj) -> str`, `resolve(token, expected_kind) -> int` (raises `ModelRetry` on wrong kind/unknown), `to_json()` / `from_json()` for Redis
- `TOKEN_RE = r"\b(PROJECT|SAMPLE|...)_(\d{4})\b"`

**Step 1.3** — `server/chat/refs.py`
- `Ref` type (annotated `str` produced only via `Pseudonymizer.token`)
- `ToolResult` base model + validator/test helper that rejects plain `str` fields

**Step 1.4** — `server/chat/store.py` ✅ (basic loop)
- Load/save `ModelMessagesTypeAdapter`-serialised history and mapping from Redis keyed by `user_id`, TTL from config (24h, refreshed on every write), keep the last `max_history_turns` (default 5) turns, also used to cap the widget display list; older ones compacted to question + answer (tool calls and results dropped; latest turn kept complete)
- Also keep a display list per user (`msg_id`, user text, pending/done) so the widget can re-render the conversation and reconnect to a still-pending stream

#### Phase 2: Agent & tools

**Step 2.1** — `server/chat/deps.py`
- `ChatDeps(user: models.User, db_handler, pseudo: Pseudonymizer, page_context: str | None)`
- `session()` context manager opening a fresh DB session per tool call

**Step 2.2** — `server/chat/agent.py` ✅ (basic loop: no tools/deps yet; page context passed as path pattern, e.g. `/projects/{id}`)
- `Agent(model, deps_type=ChatDeps, instructions=...)`; instructions include: role, "refer to entities only by exact reference e.g. PROJECT_0003", "never ask for or repeat personal data", the static workflow/status summary (Step 2.5)
- Dynamic instruction adds pseudonymised page context
- `history_processors=[scrub_user_input]` (Phase 3)

**Step 2.3** — `server/chat/tools/code.py` ✅ (available to all users; roots exposed as `server/`, `opengsync_db/`, `templates/` and `docs/` (top-level `.md` only, so `docs/plans/` and `docs/mirgation/` stay hidden); only .py/.html/.jinja*/.j2/.md/.txt files)
- `list_dir(path)`, `grep_code(pattern, path=None, max_results=50)`, `read_file(path, start=1, end=200)`
- Pure Python regex search over the allowlist (no shell), resolved-path allowlist check, line/byte caps

**Step 2.4** — `server/chat/tools/` data tools (one module per domain)
- `projects.py`: `find_my_projects(status=None, limit=20)`, `get_project(project)`
- `seq_requests.py`: `find_my_seq_requests(status=None)`, `get_seq_request(request)` incl. review/submission checklist state
- `samples.py` / `libraries.py`: `list_samples(project)`, `list_libraries(request)`, `get_library(library)`
- `experiments.py`: `get_experiment_status(experiment)` incl. checklist steps (insider-only tool, registered conditionally via `prepare`)
- Each: open session → resolve tokens → fetch → access check → build `ToolResult` with tokens → close session
- Cap all `limit`s; error messages must not contain names (use tokens)

**Step 2.5** — `server/chat/context.md` (or generated) — partly done: the system prompt has hard rules to answer only from looked-up code plus a short code map (in `agent.py`)
- Curated static summary: entity hierarchy, status enums and meaning, checklist steps. Optionally generated from enums at build time so it doesn't drift

#### Phase 3: Input scrubbing

**Step 3.1** — `server/chat/scrub.py`
- `scrub_user_input` history processor: for user-part text, replace titles/identifiers/names of entities the user can access (fuzzy, via existing `similarity` searches) with tokens (adding to mapping); regex-mask emails and phone numbers
- Optional later: Microsoft Presidio for person names in free text


#### Phase 4: Rendering (de-pseudonymisation)

**Step 4.1** — `server/chat/render.py` (Markdown → safe HTML done: raw HTML escaped, unsafe URLs dropped; token swap pending)
- `render_message(text, pseudo, db_handler, user, label_cache) -> Markup`
  1. Markdown → HTML (existing `markdown` dep), sanitise (allowlist tags)
  2. Collect tokens, resolve to db ids, batch-fetch titles per kind, re-check access
  3. `TOKEN_RE.sub` with callback → `<a href="{url}" class="entity-ref">{html.escape(title)}</a>`; unknown/revoked tokens left as-is
- Label cache per stream (in-memory; optional short Redis TTL)

#### Phase 5: Routes ✅ (implemented)

**Step 5.1** — `server/routes/htmx/chat.py`
All routes act on the current user's single conversation (no ids in the URL besides `msg_id`).
- `GET /htmx/chat` → render `components/chat/conversation.html` from the user's display list (widget open / page load); pending messages render with `assistant_html=None` so the widget reconnects to their stream
- `POST /htmx/chat/messages` (form fields `message`, `page_path`) → store pending user message, return `components/chat/message.html` (user bubble + assistant placeholder with `sse-connect`); `rate_limit` dependency; reject while a reply is still pending
- `GET /htmx/chat/stream/{msg_id}` → `msg_id` must belong to the user (404 otherwise). `StreamingResponse(media_type="text/event-stream")`, header `X-Accel-Buffering: no`; runs `agent.run_stream_events(..., message_history=..., deps=..., usage_limits=...)` (not `run_stream`, which stops at the first text and skips later tool calls), shows a status line while a tool runs, on each delta re-renders the accumulated text and emits a `message` event (full bubble HTML); `error` event on failure; `done` event at the end (closes the client stream). Stops on `request.is_disconnected()`; on completion saves pseudonymised history + mapping and refreshes the TTL
- CSRF: the widget sends `X-CSRF-Token` on every request (`dependencies.verify_csrf_header`)
- Register in `server/routes/htmx/__init__.py` with `require_user_id`

**Step 5.2** — nginx
- Prefer `X-Accel-Buffering: no` response header (no config change). If insufficient, add `location /htmx/chat/` with `proxy_buffering off;` and longer `proxy_read_timeout`

#### Phase 6: UI ✅ (implemented)

**Step 6.1** — `templates/components/chat/widget.html` + `static/js/chat.js` + `static/style/chat.css`
- Floating button in the bottom-left corner (replaces the help icon for logged-in users; help link moved into the chat header), included from `templates/base.html` when the user is logged in and `chat_enabled` is not false (wire to `chat.enabled`)
- ✨ toggle button, 🤖 in the header; one size (640px wide, full height); open state remembered in `localStorage`. No "new conversation" button
- First open shows a notice (AI, may be inaccurate, no personal data, external service, 24h retention) that must be accepted; stored in a `chat_consent` cookie for 1 year, and `POST /htmx/chat/messages` returns 403 without it
- Plain textarea input, send via `hx-post`, stream via `htmx-ext-sse`; Enter sends, Shift+Enter newline; send disabled while a reply streams
- Sends `page_path` (`location.pathname`) with each message; server resolves it to an entity and converts to a token
- Disclaimer: "Don't enter personal data. Responses may be inaccurate." Empty state notes the 24h retention

**Step 6.2** — `templates/components/chat/conversation.html`, `message.html`
- `conversation.html`: `messages: list[{msg_id, user_message, assistant_html | None}]`
- `message.html`: user bubble (escaped text) + assistant bubble; while pending, the assistant bubble connects to `/htmx/chat/stream/{msg_id}` and its innerHTML is swapped on each `message`/`error` event

#### Phase 7: Observability & audit
- Done: every user message is audited (`POST /htmx/chat/messages`, raw text in `metadata.message`, also for rejected attempts); replies are not. Per-reply tool names and token usage are logged.
- Log per turn: user id, msg id, tool names called, token usage, latency (no mapping, no real names)
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
- `services/backend/templates/components/chat/conversation.html`
- `services/backend/static/js/chat.js`
- `services/backend/static/style/chat.css`
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
17. Unauthenticated → 401/redirect; another user's `msg_id` on the stream route → 404
18. Message POST is rate-limited
19. SSE stream emits events with `text/event-stream` and `X-Accel-Buffering: no`
20. Chat disabled in config → routes not mounted, widget not rendered

#### Manual Verification
1. Open widget on several pages; ask "what are my projects?" → real titles shown as links in the UI
2. Inspect logged model requests → only tokens, no titles/names/emails
3. Mention a project by name; confirm only its token is in the stored history
4. Close the tab mid-answer → generation stops (check logs/usage)
5. Through nginx: reply streams incrementally, not all at once

---

### Later (out of scope for v1)
- **`@`-mention picker**: `GET /htmx/chat/mentions?q=...` returns accessible entities for autocomplete; the selected item inserts its token into the input (token assigned server-side in the user's mapping). Exact references instead of relying on fuzzy scrubbing; ideally shown as a labelled chip rather than the raw token
- Write actions proposed by the model and confirmed via a UI button
- MCP wrapper over the tool functions

---

### Open questions
1. **LLM provider**: hosted (needs GDPR DPA, EU residency, zero data retention) vs. self-hosted via OpenAI-compatible server (vLLM/Ollama)? Determines `pydantic-ai-slim` extra and whether pseudonymisation is the primary or secondary safeguard
2. **Who gets the chat**: all users, or insiders only for v1?
3. **Code tools for regular users**: should non-insiders be able to read code, or only data tools + static context?
4. **Which fields are acceptable to the model**: are dates, organisms, library types, sample counts OK? Are any fields (e.g. `project.identifier` like `BSF_0123`) considered non-identifying?
5. **Entity kinds in scope for v1**: projects, seq requests, samples, libraries, pools, experiments — anything else (lab preps, seq runs, files)?
