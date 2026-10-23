"""Chat usage summary for the admin chat page, read from the audit logs with DuckDB.

Every message attempt is audited by `POST /htmx/chat/messages` (see `routes/htmx/chat.py`), including rejected
ones (rate limited, no consent, too long, ...), as one JSON line in `{log_folder}/audits/YYYY-MM-DD.jsonl[.gz]`.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import duckdb

from ..core.audit_reader import audit_files

CHAT_ROUTE = "/htmx/chat/messages"
MAX_PREVIEW_LENGTH = 300

STATUS_LABELS = {
    400: "Empty or too long",
    401: "Not logged in",
    403: "No consent / CSRF",
    404: "Chat disabled",
    429: "Rate limited / reply pending",
}


@dataclass
class DayCount:
    day: date
    messages: int = 0
    rejected: int = 0
    users: int = 0


@dataclass
class UserCount:
    user_id: int | None
    messages: int
    rejected: int
    last_message: datetime


@dataclass
class PageCount:
    page: str | None
    messages: int


@dataclass
class StatusCount:
    status_code: int
    attempts: int

    @property
    def label(self) -> str:
        return STATUS_LABELS.get(self.status_code, "Error" if self.status_code >= 500 else "Rejected")


@dataclass
class RecentMessage:
    ts: datetime
    user_id: int | None
    status_code: int
    length: int | None
    page: str | None
    message: str


@dataclass
class ChatUsage:
    days: int
    messages_24h: int = 0
    messages_7d: int = 0
    messages: int = 0
    rejected: int = 0
    users_7d: int = 0
    users: int = 0
    avg_length: float | None = None
    daily: list[DayCount] = field(default_factory=list)
    top_users: list[UserCount] = field(default_factory=list)
    top_pages: list[PageCount] = field(default_factory=list)
    rejections: list[StatusCount] = field(default_factory=list)
    recent: list[RecentMessage] = field(default_factory=list)

    @property
    def max_daily(self) -> int:
        return max((d.messages + d.rejected for d in self.daily), default=0)


def summarize(audit_folder: str, now: datetime, days: int = 30, top: int = 10, recent: int = 25) -> ChatUsage:
    usage = ChatUsage(days=days)
    start = now - timedelta(days=days)
    # files are named by the server's local date; one extra day covers timezone offsets
    files = audit_files(audit_folder, since=start.date() - timedelta(days=1))

    if files:
        with duckdb.connect() as con:
            _load(con, files, start)
            _fill(con, usage, now, top=top, recent=recent)

    counts = {d.day: d for d in usage.daily}
    first_day = start.date() + timedelta(days=1)
    usage.daily = [counts.get(day, DayCount(day=day)) for day in (first_day + timedelta(days=i) for i in range(days))]
    return usage


def _load(con: duckdb.DuckDBPyConnection, files: list[str], start: datetime) -> None:
    con.execute(
        """
        CREATE TEMP TABLE chat AS
        SELECT
            ts::TIMESTAMPTZ AS ts,
            substr(ts, 1, 10)::DATE AS day,  -- the server's local date, as written
            user_id,
            status_code,
            status_code < 400 AS ok,
            TRY_CAST(metadata->>'length' AS INTEGER) AS length,
            metadata->>'page' AS page,
            coalesce(metadata->>'message', '') AS message,
        FROM read_json(
            ?,
            format = 'newline_delimited',
            columns = {
                ts: 'VARCHAR', user_id: 'BIGINT', method: 'VARCHAR', route: 'VARCHAR',
                status_code: 'INTEGER', metadata: 'JSON',
            },
            ignore_errors = true
        )
        WHERE route = ? AND method = 'POST' AND ts IS NOT NULL AND ts::TIMESTAMPTZ >= ?
        """,
        [files, CHAT_ROUTE, start],
    )


def _fill(con: duckdb.DuckDBPyConnection, usage: ChatUsage, now: datetime, top: int, recent: int) -> None:
    row = con.execute(
        """
        SELECT
            count(*) FILTER (ok AND ts >= $day),
            count(*) FILTER (ok AND ts >= $week),
            count(*) FILTER (ok),
            count(*) FILTER (NOT ok),
            count(DISTINCT user_id) FILTER (ok AND ts >= $week),
            count(DISTINCT user_id) FILTER (ok),
            avg(length) FILTER (ok),
        FROM chat
        """,
        {"day": now - timedelta(days=1), "week": now - timedelta(days=7)},
    ).fetchone()
    assert row is not None
    (
        usage.messages_24h, usage.messages_7d, usage.messages, usage.rejected,
        usage.users_7d, usage.users, usage.avg_length,
    ) = row

    usage.daily = [
        DayCount(*r) for r in con.execute(
            """
            SELECT day, count(*) FILTER (ok), count(*) FILTER (NOT ok), count(DISTINCT user_id) FILTER (ok)
            FROM chat GROUP BY day
            """
        ).fetchall()
    ]
    usage.top_users = [
        UserCount(*r) for r in con.execute(
            """
            SELECT user_id, count(*) FILTER (ok) AS messages, count(*) FILTER (NOT ok), max(ts)
            FROM chat GROUP BY user_id ORDER BY messages DESC, max(ts) DESC LIMIT ?
            """,
            [top],
        ).fetchall()
    ]
    usage.top_pages = [
        PageCount(*r) for r in con.execute(
            "SELECT page, count(*) AS n FROM chat WHERE ok GROUP BY page ORDER BY n DESC, page LIMIT ?",
            [top],
        ).fetchall()
    ]
    usage.rejections = [
        StatusCount(*r) for r in con.execute(
            "SELECT status_code, count(*) AS n FROM chat WHERE NOT ok GROUP BY status_code ORDER BY n DESC"
        ).fetchall()
    ]
    usage.recent = [
        RecentMessage(*r) for r in con.execute(
            "SELECT ts, user_id, status_code, length, page, left(message, ?) FROM chat ORDER BY ts DESC LIMIT ?",
            [MAX_PREVIEW_LENGTH, recent],
        ).fetchall()
    ]
