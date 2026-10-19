# AI Support Chat

How the floating assistant works: a support chat on every page that answers questions about the platform by reading its source code and documentation. It runs as a Pydantic AI agent inside the backend, streams replies over Server-Sent Events, and cannot see or change any records.

- [Overview](#overview)
- [Configuration](#configuration)
- [Request flow](#request-flow)
- [Agent](#agent)
- [Code tools](#code-tools)
- [Conversation storage](#conversation-storage)
- [Streaming](#streaming)
- [Widget](#widget)
- [Privacy and abuse protection](#privacy-and-abuse-protection)
- [Code](#code)
- [Tests](#tests)
- [Not implemented](#not-implemented)

## Overview

- **What it answers:** how the platform works: statuses, form fields, workflow steps, permissions, what a page or button does, and file formats. The agent must base these answers on code it looked up in the same conversation, not on general knowledge.
- **What it can access:** only a read-only, allowlisted view of the source code and the top-level files in `docs/` (see [Code tools](#code-tools)). It has no database access and no tools that write anything. It never sees the user's projects, samples or other data.
- **Who gets it:** every logged-in user, when `chat.enabled` is set. Staff (insiders) get instructions that cover internal workflows. Clients get instructions that describe staff steps only at a high level.
- **One conversation per user:** stored in Redis under the user's id. It expires `history_ttl_hours` after the last message. There are no conversation ids and no "new conversation" button.
- **No MCP:** the tools are plain Python functions registered on the agent. The backend is the only client.

## Configuration

`chat:` section in `opengsync.yaml` (`ChatConfig` in `server/core/config.py`):

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `false` | Mounts the routes (they return 404 otherwise), renders the widget and builds the agent at startup. |
| `model` | `"test"` | `"test"` is an offline echo model with no LLM. Otherwise a pydantic-ai model string (e.g. `openai:gpt-4.1-mini`; hosted providers read their usual env var, such as `OPENAI_API_KEY`), or, together with `base_url`, the model name served by an OpenAI-compatible endpoint. |
| `base_url` | `null` | OpenAI-compatible endpoint (self-hosted or proxy). The API key comes from the `CHAT_API_KEY` env var. |
| `continuous_usage_stats` | `false` | Set to `true` for **vLLM** endpoints only. vLLM sends cumulative usage in every streamed chunk, and the flag tells pydantic-ai to replace usage instead of adding it up. Other endpoints reject the `stream_options.continuous_usage_stats` parameter. |
| `history_ttl_hours` | `72` | How long a conversation is kept after the last message. Also shown in the consent notice. |
| `max_history_turns` | `5` | Turns (question + answer) kept, both in the widget and in the history sent to the model. |
| `max_requests_per_turn` | `25` | Model requests per reply. Each tool-call round trip counts as one. |

```yaml
chat:
  enabled: true
  model: my-model
  base_url: https://llm.example.org/v1
  continuous_usage_stats: false  # true for vLLM
```

The agent is built once at startup (`lifespan.py` → `app.state.chat_agent`) and injected with `dependencies.chat_agent`. Changing the config means restarting the app.

## Request flow

```
[widget (HTMX + htmx-ext-sse)]
   │ GET  /htmx/chat                 → components/chat/conversation.html (the user's conversation)
   │ POST /htmx/chat/messages        → stores a pending message, returns components/chat/message.html
   │                                   (user bubble + assistant placeholder that connects to the stream)
   │ GET  /htmx/chat/stream/{msg_id} → SSE: "message" (full re-rendered reply), "error", "done"
   ▼
[server/routes/htmx/chat.py] ── ChatDeps(user_role, page, form) ──► Agent ──► LLM
                                                                     │
                                                    tools: list_dir / grep_code / read_file
```

All routes need a logged-in user (`require_user_id` on the router) and act on that user's own conversation.

**`POST /htmx/chat/messages`** (form fields `message`, `page_path`, `form_path`), checked in this order:

1. The message is audited with its raw text (before any other check, so rejected attempts are logged too).
2. The `X-CSRF-Token` header must match the `csrf_token` cookie (`verify_csrf_header`).
3. Rate limit: 10 per minute, 100 per hour.
4. The `chat_consent=1` cookie must be present (403 otherwise).
5. The message must not be empty and at most 4000 characters long.
6. No other reply may still be pending (429).

`page_path` and `form_path` are mapped to **route patterns** (`_route_pattern`, e.g. `/projects/{project_id}`). The URL itself is never stored or passed to the model, because path segments can contain record ids, share or reset tokens, or file names. Paths that match no route are dropped. The app's `root_path` prefix is removed before matching.

**`GET /htmx/chat/stream/{msg_id}`**: returns 404 for a `msg_id` that is not in the current user's conversation. If the reply is already finished, it sends the final HTML and `done`. If another stream is already generating it (e.g. a second tab), it waits for that stream and sends the result. Otherwise it generates the reply (see [Streaming](#streaming)).

## Agent

`server/chat/agent.py`, `build_agent()`:

- **Model:** `_build_model()`. `"test"` returns a `FunctionModel` that echoes the prompt. With `base_url` it builds an `OpenAIChatModel` with an `OpenAIProvider`. Otherwise the model string goes to pydantic-ai as is (`defer_model_check=True`, so a missing provider key only fails on the first request).
- **Static instructions** (`INSTRUCTIONS`, filled with the organization name and contact email):
  - Answers about the platform must be based on code looked up with the tools in this conversation. The tools may be skipped only for greetings, thanks and follow-ups about something already looked up.
  - Before answering, check that every claim is backed by code that was read. If something can't be confirmed, say so and point the user to the facility's email address.
  - How to look things up (grep → read the relevant lines → check the template for what the user sees), plus a short code map.
  - Answer in terms of the web interface, not code, unless asked. Answer in Markdown. Never ask for or repeat personal data.
- **Dynamic instructions** (`context_instructions`, rebuilt on every request):
  - Insider or client instructions, chosen by `user_role.insider`.
  - The route pattern of the page the user is on, and of the form or workflow step open in a modal, so questions like "what do I enter here?" can be looked up.
  - On the last allowed request (`max_requests_per_turn - 1` requests used): an instruction to answer now with what was found.
- **Last request without tools:** the `PrepareTools` capability hides all tools on the last allowed request. The model then has to answer, so a long lookup ends with an answer instead of `UsageLimitExceeded`. If the limit is still exceeded, the stream route appends a "couldn't finish looking this up" note as a fallback.
- **`ChatDeps`** carries only `user_role`, `page` and `form`. No user id, name or email reaches the agent.

## Code tools

`server/chat/tools/code.py`. Paths are virtual: the first segment names an allowlisted root.

| Root | Contents |
|---|---|
| `server/` | Backend package (routes, forms, workflows, core) |
| `opengsync_db/` | Database package (models, categories, queries, blueprints) |
| `templates/` | Jinja2 templates |
| `docs/` | Top-level files of `docs/` only, so `docs/plans/` and `docs/mirgation/` stay hidden. **This file is readable by the assistant.** |

| Tool | Does | Limits |
|---|---|---|
| `list_dir(path="")` | Lists a directory. With an empty path, lists the roots with descriptions. | 300 entries |
| `grep_code(pattern, path="", ignore_case=True, max_results=50)` | Regex search, returns `path:line: text` | Pattern ≤ 200 chars, ≤ 100 results, 5 s time budget (`regex` module with timeouts, so a bad pattern can't hang a worker), lines cut at 300 chars |
| `read_file(path, start_line=1, end_line=None)` | Returns lines with line numbers | ≤ 400 lines per call, lines cut at 300 chars |

Safety rules, applied by every tool:

- Paths are resolved and checked with `Path.is_relative_to(root)`, so `..`, absolute paths and symlinks pointing outside a root are refused.
- Only `.py`, `.html`, `.jinja`, `.jinja2`, `.j2`, `.md` and `.txt` files are listed, searched or read.
- Dotfiles, dot-directories and `__pycache__` are hidden.
- Errors raise `ModelRetry` with a hint (e.g. "use list_dir to find files"), so the model can correct itself.

## Conversation storage

`server/chat/store.py`, `ChatStore(redis, user_id)`:

| Key | Content |
|---|---|
| `chat:{user_id}:messages` | Display list of `ChatMessage` (`id`, `user_message`, `assistant_text`, `status` = `pending`/`done`/`error`, `page`, `form`, `created_at`), used to render the widget |
| `chat:{user_id}:history` | pydantic-ai `ModelMessage`s sent back to the model with follow-ups |
| `chat:{user_id}:lock` | `msg_id` of the reply being generated (`SET NX`, expires after 5 minutes) |

- Every write refreshes the TTL of `messages` and `history` to `history_ttl_hours`.
- Both lists keep the last `max_history_turns` turns. In the history, older turns are **compacted** to question and answer text (tool calls and their often large results are dropped). The latest turn stays complete, so a follow-up question can use what was just looked up without searching again.
- **Stale replies:** a `pending` message older than the lock timeout with no lock held is marked `error` when the conversation is loaded or a new message is posted. A crashed worker therefore can't block the conversation.

## Streaming

`_generate_reply` in `server/routes/htmx/chat.py`:

- Uses `agent.run_stream_events(...)`, not `run_stream`, which stops at the first text part and skips later tool calls. The history comes from Redis, and the usage limit is `max_requests_per_turn`.
- Text parts from all model responses (e.g. a short note before a tool call, then the answer) are concatenated. **On each event the whole accumulated text is re-rendered** to HTML and sent as one `message` event, which the bubble swaps in as its innerHTML. Text events are debounced to one every 0.1 s.
- While a tool runs, a status line is appended ("Searching the code for …", "Reading …", "Browsing …"). After the tool result comes back, typing dots show while the model thinks.
- **Heartbeat:** when no event arrives for 15 s (e.g. a long thinking phase), an SSE comment (`: keep-alive`) is sent so nginx doesn't close the idle connection (`proxy_read_timeout`, 60 s by default). `_with_heartbeat` waits without cancelling the pending event.
- **Disconnects:** the stream stops when `request.is_disconnected()`, and the message is marked `error`. The lock is always released.
- **On success:** saves `run.all_messages()` as the history, marks the message `done`, logs the tool names and token usage, and sends the final HTML followed by `done`.
- **On errors:** logs the exception, marks the message `error` and sends an `error` event with whatever text was produced plus "The response was interrupted.", followed by `done`.
- Response headers: `Cache-Control: no-cache`, `X-Accel-Buffering: no`, so nginx doesn't buffer the stream. No nginx config change is needed.
- The generator runs after the request's dependencies are torn down, so it opens its own Redis connection from `app.state.redis_pool`.

**Rendering** (`server/chat/render.py`, `render_markdown`): Markdown with `fenced_code`, `tables` and `sane_lists`. Raw HTML in model output is treated as text. `href`/`src` attributes that don't start with `http://`, `https://`, `mailto:`, `/` or `#` are dropped, and external links open in a new tab with `rel="noopener noreferrer"`. User messages are rendered as escaped plain text.

## Widget

`templates/components/chat/widget.html`, `static/js/chat.js`, `static/style/chat.css`. Included from `base.html` for logged-in users when `chat_enabled` is set.

- A ✨ button in the bottom-left corner opens the panel. The help link moved into the panel header. The open state is remembered in `localStorage` (`chat:open`).
- **Consent:** the first time the panel opens, a notice explains that the assistant is an AI that may be inaccurate, that no personal data should be entered, that messages go to an external AI service and are audited, that it can't see or change data, and how long conversations are kept. Accepting sets the `chat_consent=1` cookie for one year. The server refuses messages without it.
- **Input:** a textarea that grows with its content. Enter sends, Shift+Enter adds a newline. Sending is disabled while a reply streams. Messages are posted with `hx-post`, and every request carries the `X-CSRF-Token` header.
- **Context:** `page_path` is `location.pathname`. `form_path` is where the form in the topmost open modal submits: its `data-submit-url`, otherwise the first `hx-post`/`hx-put`/`hx-patch`. Forms that submit from JavaScript set `data-submit-url` (spreadsheet component, BA report, share project data, edit kit barcodes, barcode constraints). When adding such a form, add the attribute too, or the assistant won't know which form the user means.
- **Reconnect:** loading the conversation renders pending messages with a streaming placeholder, so a page reload reconnects to a running reply.
- **Errors:** a 429 or other failed request shows an error bubble, unless the server already showed a flash toast. An SSE connection error replaces the bubble, so the sse extension stops retrying.
- All URLs are built with `url_for`, so the widget works when the app runs behind a path prefix.

## Privacy and abuse protection

- No record data reaches the model: there are no data tools. The model gets only the user's role and route patterns, never URLs, ids, names or emails.
- Users are told not to enter personal data (consent notice, disclaimer below the input). The text they type still goes to the configured LLM provider as is.
- Every message attempt is written to the audit log with its raw text (cut at 10,000 characters), page and form. Replies are not audited. Per reply, tool names and token usage are logged.
- Rate limit, the one-pending-reply rule, the per-reply request limit and the history cap bound the cost per user.
- The code tools are read-only and allowlisted, and `.env`, config, data, uploads, logs, media and tests are outside every root.

## Code

| File | Contents |
|---|---|
| `server/chat/agent.py` | `build_agent`, instructions, `ChatDeps`, model construction |
| `server/chat/tools/code.py` | `list_dir`, `grep_code`, `read_file` |
| `server/chat/store.py` | `ChatStore`, `ChatMessage`, history compaction, stream lock |
| `server/chat/render.py` | Safe Markdown rendering |
| `server/routes/htmx/chat.py` | Routes, SSE streaming, heartbeat, route-pattern mapping, audit |
| `server/core/config.py` | `ChatConfig`, `CHAT_API_KEY` |
| `server/core/lifespan.py` | Builds the agent; `chat_enabled` / `chat_history_ttl_hours` template globals |
| `server/core/dependencies.py` | `chat_agent`, `verify_csrf_header` |
| `templates/components/chat/` | `widget.html`, `conversation.html`, `message.html` |
| `static/js/chat.js`, `static/style/chat.css` | Widget behaviour and styles |

## Tests

No test calls a real LLM. They use a scripted `FunctionModel`.

- `services/pytest/tests/server/test_chat_unit.py`: code-tool allowlist and refusals (hidden entries, symlinks, flat `docs/`, line caps, grep time budget), Markdown sanitising, history compaction, heartbeat.
- `services/pytest/tests/server/test_chat_routes.py`: login, 404 when disabled, CSRF, consent, other users' messages, validation, rate limit, the full conversation loop, one pending reply at a time, history on follow-ups, model errors, tool status, tools hidden on the last request, usage-limit fallback, role-specific instructions, no personal data in instructions, page and form context limited to route patterns, auditing, path prefix.

## Not implemented

Ideas from the original plan that were not built. If data access is ever added, they are the intended design:

- **Read-only data tools** (projects, requests, samples, libraries, experiments) running with the user's permissions, through `Q.<model>.permissions` / access levels and one DB session per tool call.
- **Pseudonymisation:** tools return per-conversation tokens (`PROJECT_0001`, …) instead of names or identifiers. Tokens are swapped back to escaped links only when rendering HTML, after re-checking access.
- **Input scrubbing:** a history processor that replaces entity names in user messages with tokens and masks emails and phone numbers.
- An `@`-mention picker that inserts tokens, write actions proposed by the model and confirmed by the user, and an MCP wrapper over the tools.
