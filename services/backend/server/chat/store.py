"""Per-user chat persistence in Redis: one conversation per user, expiring after `chat.history_ttl_hours`.

Keys:
    chat:{user_id}:messages   display list (user text, assistant text, status) used to render the widget
    chat:{user_id}:history    pydantic-ai ModelMessages fed back to the agent
    chat:{user_id}:lock       held while a reply is being generated
"""
from datetime import datetime, timedelta
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field
from pydantic_ai import ModelMessage, ModelMessagesTypeAdapter, ModelRequest, ModelResponse, TextPart, UserPromptPart

from ..core import config
from ..core.redis import RedisClient

STREAM_LOCK_SECONDS = 5 * 60


class ChatMessage(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    user_message: str
    assistant_text: str = ""
    status: Literal["pending", "done", "error"] = "pending"
    page: str | None = None  # route pattern only (never the URL, which can contain tokens or file names)
    form: str | None = None  # route pattern of the form/workflow step open in a modal, if any
    created_at: datetime = Field(default_factory=config.settings.now)


class _MessageList(BaseModel):
    messages: list[ChatMessage] = []


class ChatStore:
    def __init__(self, r: RedisClient, user_id: int):
        self.r = r
        self.user_id = user_id
        self.ttl = config.settings.app_config.chat.history_ttl_hours * 3600

    def _key(self, name: str) -> str:
        return f"chat:{self.user_id}:{name}"

    def _touch(self) -> None:
        for name in ("messages", "history"):
            self.r.expire(self._key(name), self.ttl)

    # ── display messages ───────────────────────────────────────────

    def messages(self) -> list[ChatMessage]:
        if (data := self.r.get(self._key("messages"))) is None:
            return []
        return _MessageList.model_validate_json(data).messages  # type: ignore[arg-type]

    def _save_messages(self, messages: list[ChatMessage]) -> None:
        data = _MessageList(messages=messages[-config.settings.app_config.chat.max_history_turns:]).model_dump_json()
        self.r.set(self._key("messages"), data, ex=self.ttl)
        self._touch()

    def get(self, msg_id: str) -> ChatMessage | None:
        return next((m for m in self.messages() if m.id == msg_id), None)

    def add(self, message: ChatMessage) -> None:
        self._save_messages(self.messages() + [message])

    def update(self, message: ChatMessage) -> None:
        self._save_messages([message if m.id == message.id else m for m in self.messages()])

    def pending(self) -> ChatMessage | None:
        """The message currently awaiting a reply. Stale pending messages (no live stream) are marked as failed."""
        for message in self.messages():
            if message.status != "pending":
                continue
            stale = config.settings.now() - message.created_at > timedelta(seconds=STREAM_LOCK_SECONDS)
            if stale and not self.is_locked():
                message.status = "error"
                self.update(message)
                continue
            return message
        return None

    # ── agent history ──────────────────────────────────────────────

    def history(self) -> list[ModelMessage]:
        if (data := self.r.get(self._key("history"))) is None:
            return []
        return ModelMessagesTypeAdapter.validate_json(data)  # type: ignore[arg-type]

    def save_history(self, messages: list[ModelMessage]) -> None:
        messages = compact_history(messages, config.settings.app_config.chat.max_history_turns)
        self.r.set(self._key("history"), ModelMessagesTypeAdapter.dump_json(messages), ex=self.ttl)
        self._touch()

    # ── stream lock ────────────────────────────────────────────────

    def acquire_lock(self, msg_id: str) -> bool:
        return bool(self.r.set(self._key("lock"), msg_id, nx=True, ex=STREAM_LOCK_SECONDS))

    def release_lock(self) -> None:
        self.r.delete(self._key("lock"))

    def is_locked(self) -> bool:
        return bool(self.r.exists(self._key("lock")))


def _is_user_prompt(message: ModelMessage) -> bool:
    return isinstance(message, ModelRequest) and any(isinstance(p, UserPromptPart) for p in message.parts)


def _split_turns(messages: list[ModelMessage]) -> list[list[ModelMessage]]:
    """Split a history into turns, each starting with the user's prompt."""
    turns: list[list[ModelMessage]] = []
    for message in messages:
        if _is_user_prompt(message) or not turns:
            turns.append([])
        turns[-1].append(message)
    return turns


def _compact_turn(turn: list[ModelMessage]) -> list[ModelMessage]:
    """Reduce a turn to the user's prompt and the assistant's text, dropping tool calls and their (large) results."""
    prompt = next((p for m in turn if isinstance(m, ModelRequest) for p in m.parts if isinstance(p, UserPromptPart)), None)
    text = "\n\n".join(
        p.content for m in turn if isinstance(m, ModelResponse) for p in m.parts if isinstance(p, TextPart) and p.content.strip()
    )
    if prompt is None or not text:
        return []
    return [ModelRequest(parts=[prompt]), ModelResponse(parts=[TextPart(content=text)])]


def compact_history(messages: list[ModelMessage], max_turns: int) -> list[ModelMessage]:
    """Keep the last `max_turns` turns. Older turns are reduced to question and answer; the latest turn stays
    complete, so follow-up questions can use what was just looked up without searching again."""
    turns = _split_turns(messages)[-max_turns:]
    compacted: list[ModelMessage] = []
    for turn in turns[:-1]:
        compacted.extend(_compact_turn(turn))
    if turns:
        compacted.extend(turns[-1])
    return compacted
