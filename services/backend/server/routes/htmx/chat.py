import asyncio
import time
from typing import AsyncIterator, TypeVar

from fastapi import APIRouter, Depends
from fastapi.routing import APIRoute
from starlette.routing import Match
from fastapi.responses import Response, StreamingResponse
from loguru import logger
from markupsafe import Markup
from pydantic_ai import (
    Agent, FunctionToolCallEvent, FunctionToolResultEvent, PartDeltaEvent, PartStartEvent,
    TextPart, TextPartDelta, ToolCallPart, UsageLimitExceeded, UsageLimits,
)

from opengsync_db import models

from ...core import dependencies, responses, runtime, config, redis as rds, audit, exceptions as exc
from ... import chat

MAX_MESSAGE_LENGTH = 4000
CONSENT_COOKIE = "chat_consent"  # set by the widget when the user accepts the notice
MAX_AUDITED_MESSAGE_LENGTH = 10_000  # longer (rejected) messages are cut in the audit log
WAIT_POLL_SECONDS = 1.0
STREAM_DEBOUNCE_SECONDS = 0.1
# nginx closes proxied connections after 60s without data (proxy_read_timeout), e.g. while the model thinks
HEARTBEAT_SECONDS = 15.0
HEARTBEAT = ": keep-alive\n\n"  # SSE comment, ignored by the browser
# shown while the model works without streaming text, e.g. thinking between tool calls
THINKING = Markup('<p class="chat-thinking"><span class="chat-typing"><span></span><span></span><span></span></span></p>')

T = TypeVar("T")


def require_chat_enabled() -> None:
    if not config.settings.app_config.chat.enabled:
        raise exc.NotFoundException()


router = APIRouter(prefix="/chat", tags=["chat"], dependencies=[Depends(require_chat_enabled)])


def _assistant_html(message: chat.ChatMessage) -> Markup | None:
    if message.status == "pending":
        return None
    html = chat.render_markdown(message.assistant_text) if message.assistant_text else Markup("")
    if message.status == "error":
        html += Markup('<p class="chat-error-note"><i class="bi bi-exclamation-triangle"></i> The response was interrupted.</p>')
    return html


@router.get("", name="chat_conversation")
def get_conversation(
    user_id: int = Depends(dependencies.require_user_id),
    r: rds.RedisClient = Depends(dependencies.redis),
) -> Response:
    store = chat.ChatStore(r, user_id)
    store.pending()  # marks stale pending messages as failed
    messages = [
        {"msg_id": m.id, "user_message": m.user_message, "assistant_html": _assistant_html(m)}
        for m in store.messages()
    ]
    return responses.htmx_response(template="components/chat/conversation.html", messages=messages)


def audit_message(request: runtime.Request) -> audit.AuditLogger:
    """Audit every message attempt with the raw text, to spot abuse. Runs before the CSRF and rate-limit checks,
    so rejected attempts are logged with their text too."""
    audit_logger = dependencies.audit_log(request)
    raw = str((request.state.form_data or {}).get("message") or "")
    audit_logger.metadata = {"message": raw[:MAX_AUDITED_MESSAGE_LENGTH], "length": len(raw)}
    if len(raw) > MAX_AUDITED_MESSAGE_LENGTH:
        audit_logger.metadata["truncated"] = True
    return audit_logger


@router.post(
    "/messages",
    name="chat_post_message",
    dependencies=[
        Depends(audit_message),
        Depends(dependencies.verify_csrf_header),
        Depends(dependencies.rate_limit("10/minute", "100/hour")),
    ],
)
def post_message(
    request: runtime.Request,
    user_id: int = Depends(dependencies.require_user_id),
    r: rds.RedisClient = Depends(dependencies.redis),
    audit_logger: audit.AuditLogger = Depends(audit_message),
) -> Response:
    if request.cookies.get(CONSENT_COOKIE) != "1":
        raise exc.NoPermissionsException("Please accept the assistant notice first.")

    form = request.state.form_data or {}
    text = str(form.get("message") or "").strip()
    if not text:
        raise exc.BadRequestException("Message is empty.")
    if len(text) > MAX_MESSAGE_LENGTH:
        raise exc.BadRequestException(f"Message is too long (max {MAX_MESSAGE_LENGTH} characters).")

    store = chat.ChatStore(r, user_id)
    if store.pending() is not None:
        raise exc.TooManyRequestsException("Please wait for the current reply to finish.")

    page = _route_pattern(request, str(form.get("page_path") or "") or None)
    # the form/workflow step open in a modal, identified by the URL it posts to
    open_form = _route_pattern(request, str(form.get("form_path") or "") or None, methods=("POST", "PUT", "PATCH"))
    message = chat.ChatMessage(user_message=text, page=page, form=open_form)
    store.add(message)
    audit_logger.resource_id = message.id
    audit_logger.metadata["page"] = page
    audit_logger.metadata["form"] = open_form

    return responses.htmx_response(
        template="components/chat/message.html",
        msg_id=message.id, user_message=message.user_message, assistant_html=None,
    )


def _route_pattern(request: runtime.Request, url_path: str | None, methods: tuple[str, ...] = ("GET",)) -> str | None:
    """Route pattern of a URL path, e.g. `/browser/{subpath:path}`. The URL itself is never passed on:
    path segments can hold record ids, share/reset tokens or folder and file names."""
    if not url_path or not url_path.startswith("/"):
        return None
    path = url_path.split("?")[0]
    root_path = request.scope.get("root_path", "")
    if root_path and path.startswith(root_path):
        path = path[len(root_path):] or "/"
    for method in methods:
        for candidate in dict.fromkeys([path, path.rstrip("/") or "/", path.rstrip("/") + "/"]):  # routes may end in "/"
            scope = {"type": "http", "path": candidate, "method": method, "root_path": ""}
            for route in request.app.routes:
                if isinstance(route, APIRoute) and route.matches(scope)[0] == Match.FULL:
                    return route.path
    return None


def _sse(event: str, data: str = "") -> str:
    lines = data.splitlines() or [""]
    return f"event: {event}\n" + "".join(f"data: {line}\n" for line in lines) + "\n"


async def _with_heartbeat(events: AsyncIterator[T], interval: float = HEARTBEAT_SECONDS) -> AsyncIterator[T | None]:
    """Yield the items of `events`, plus None whenever `interval` seconds pass without one.
    Waiting doesn't cancel the pending item (unlike `asyncio.wait_for`)."""
    iterator = aiter(events)
    pending = asyncio.ensure_future(anext(iterator))
    try:
        while True:
            done, _ = await asyncio.wait({pending}, timeout=interval)
            if not done:
                yield None
                continue
            try:
                item = pending.result()
            except StopAsyncIteration:
                return
            yield item
            pending = asyncio.ensure_future(anext(iterator))
    finally:
        if not pending.done():
            pending.cancel()


def _final_events(message: chat.ChatMessage) -> list[str]:
    return [_sse("message", str(_assistant_html(message) or "")), _sse("done")]


@router.get("/stream/{msg_id}", name="chat_stream")
def stream_reply(
    msg_id: str,
    request: runtime.Request,
    current_user: models.User = Depends(dependencies.require_user),
    r: rds.RedisClient = Depends(dependencies.redis),
    agent: Agent[chat.ChatDeps, str] = Depends(dependencies.chat_agent),
) -> StreamingResponse:
    user_id = current_user.id
    store = chat.ChatStore(r, user_id)
    if (message := store.get(msg_id)) is None:
        raise exc.NotFoundException("Message not found.")

    if message.status != "pending":
        events = _final_events(message)
    elif not store.acquire_lock(msg_id):
        events = _wait_for_reply(request, user_id, msg_id)  # another stream is already generating this reply
    else:
        deps = chat.ChatDeps(user_role=current_user.role, page=message.page, form=message.form)
        events = _generate_reply(request, agent, deps, user_id, message)

    return StreamingResponse(
        events,  # type: ignore[arg-type]
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _tool_status(call: ToolCallPart) -> Markup:
    args = call.args_as_dict()
    if call.tool_name == "grep_code":
        label = Markup("Searching the code for <code>{}</code>").format(args.get("pattern", ""))
    elif call.tool_name == "read_file":
        label = Markup("Reading <code>{}</code>").format(args.get("path", ""))
    elif call.tool_name == "list_dir":
        label = Markup("Browsing <code>{}</code>").format(args.get("path") or "/")
    else:
        label = Markup("Running <code>{}</code>").format(call.tool_name)
    return Markup('<p class="chat-tool-status"><span class="spinner-border spinner-border-sm"></span> {}…</p>').format(label)


async def _generate_reply(
    request: runtime.Request, agent: Agent[chat.ChatDeps, str], deps: chat.ChatDeps, user_id: int, message: chat.ChatMessage,
) -> AsyncIterator[str]:
    # Runs after the request's dependencies are torn down, so it opens its own Redis connection.
    cfg = config.settings.app_config.chat
    texts: list[str] = []  # text parts of all model responses (e.g. a short note before a tool call, then the answer)
    status: Markup | None = None
    tool_calls: list[str] = []
    last_emit = 0.0

    def render() -> str:
        message.assistant_text = "\n\n".join(t for t in texts if t.strip())
        html = chat.render_markdown(message.assistant_text)
        return str(html + status if status else html)

    with rds.RedisClient(pool=request.app.state.redis_pool) as r:
        store = chat.ChatStore(r, user_id)
        try:
            async with agent.run_stream_events(
                message.user_message,
                message_history=store.history(),
                deps=deps,
                usage_limits=UsageLimits(request_limit=cfg.max_requests_per_turn),
            ) as run:
                async for event in _with_heartbeat(run):
                    force = False
                    if event is None:
                        if await request.is_disconnected():
                            return
                        yield HEARTBEAT
                        continue
                    elif isinstance(event, PartStartEvent) and isinstance(event.part, TextPart):
                        texts.append(event.part.content)
                        status = None
                    elif isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
                        if not texts:
                            texts.append("")
                        texts[-1] += event.delta.content_delta
                        status = None
                    elif isinstance(event, FunctionToolCallEvent):
                        status, force = _tool_status(event.part), True
                        tool_calls.append(event.part.tool_name)
                    elif isinstance(event, FunctionToolResultEvent):
                        status, force = THINKING, True
                    else:
                        continue

                    if await request.is_disconnected():
                        return
                    if force or time.monotonic() - last_emit >= STREAM_DEBOUNCE_SECONDS:
                        last_emit = time.monotonic()
                        yield _sse("message", render())

                status = None
                render()
                message.status = "done"
                store.save_history(run.all_messages())
                store.update(message)
            logger.info(f"Chat reply for user {user_id}: tools={tool_calls}, usage={run.usage}")
            for event in _final_events(message):
                yield event
        except UsageLimitExceeded:
            # Backstop only: tools are hidden on the last allowed request, so the model normally answers in time
            logger.warning(f"Chat reply for user {user_id} hit the usage limit: tools={tool_calls}")
            email = config.settings.app_config.personalization.email
            texts.append(
                f"*I couldn't finish looking this up. Please try a more specific question, or write to {email}.*"
            )
            status = None
            render()
            message.status = "done"
            store.update(message)
            for event in _final_events(message):
                yield event
        except Exception:
            logger.exception(f"Chat reply failed for user {user_id}")
            message.status = "error"
            store.update(message)
            yield _sse("error", str(_assistant_html(message)))
            yield _sse("done")
        finally:
            if message.status == "pending":  # client disconnected mid-stream
                message.status = "error"
                store.update(message)
            store.release_lock()


async def _wait_for_reply(request: runtime.Request, user_id: int, msg_id: str) -> AsyncIterator[str]:
    with rds.RedisClient(pool=request.app.state.redis_pool) as r:
        store = chat.ChatStore(r, user_id)
        last_heartbeat = time.monotonic()
        while not await request.is_disconnected():
            if time.monotonic() - last_heartbeat >= HEARTBEAT_SECONDS:
                last_heartbeat = time.monotonic()
                yield HEARTBEAT
            if (message := store.get(msg_id)) is None:
                yield _sse("done")
                return
            if message.status == "pending" and not store.is_locked():
                message.status = "error"  # the generating stream died without finishing
                store.update(message)
            if message.status != "pending":
                for event in _final_events(message):
                    yield event
                return
            await asyncio.sleep(WAIT_POLL_SECONDS)
