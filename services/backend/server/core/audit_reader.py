"""Read the audit logs back with DuckDB, e.g. for the audit log viewer on the admin page.

Audit lines are written by `core/middleware.py` (`_write_audit_log`) to `{log_folder}/audits/YYYY-MM-DD.jsonl`, one
flat JSON object per request, and compressed to `.jsonl.gz` after two days. See `docs/audits.md` for the format.
"""
import json
import math
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, tzinfo
from typing import Any, Literal

import duckdb

from opengsync_db.models.Base import Base

METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "PROPFIND", "LOCK", "UNLOCK")
OPS = ("insert", "update", "delete")
STATUSES = ("ok", "error")
MAX_RANGE_DAYS = 366
DEFAULT_DAYS = 7
FILTERS = ("start", "end", "user_id", "method", "status", "route", "ip", "table", "row_id", "op", "share")
TABLE_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]*$")

COLUMNS = {
    "ts": "VARCHAR",
    "user_id": "BIGINT",
    "method": "VARCHAR",
    "path": "VARCHAR",
    "route": "VARCHAR",
    "status_code": "INTEGER",
    "process_time": "DOUBLE",
    "resource_id": "VARCHAR",
    "metadata": "JSON",
    # ids are ints, uuid strings or lists (composite keys), so they are kept as JSON
    "changes": 'STRUCT("table" VARCHAR, op VARCHAR, count BIGINT, ids JSON[], fields VARCHAR[], bulk BOOLEAN)[]',
    "query_params": "JSON",
    "ip": "VARCHAR",
    "agent": "VARCHAR",
}


def audit_files(audit_folder: str, since: date, until: date | None = None) -> list[str]:
    """Audit files written from `since` to `until` (inclusive), by the date in their name (`YYYY-MM-DD.jsonl[.gz]`)."""
    if not os.path.isdir(audit_folder):
        return []
    files = []
    for name in os.listdir(audit_folder):
        if not (name.endswith(".jsonl") or name.endswith(".jsonl.gz")):
            continue
        try:
            file_date = date.fromisoformat(name[:10])
        except ValueError:
            continue
        if file_date >= since and (until is None or file_date <= until):
            files.append(os.path.join(audit_folder, name))
    return sorted(files)


def read_json_sql(param: str = "?") -> str:
    """`read_json(...)` over the list of files given as parameter `param`, with every audit column typed."""
    columns = ", ".join(f"{name}: '{type_}'" for name, type_ in COLUMNS.items())
    return (
        f"read_json({param}, format = 'newline_delimited', columns = {{{columns}}}, ignore_errors = true)"
    )


def known_tables() -> list[str]:
    return sorted(Base.metadata.tables.keys())


@dataclass
class AuditFilter:
    start: date
    end: date
    user_id: int | None = None
    method: str | None = None
    status: Literal["ok", "error"] | None = None
    route: str | None = None
    ip: str | None = None
    table: str | None = None
    row_id: str | None = None
    op: str | None = None
    share: str | None = None

    def validate(self) -> None:
        """Raises ValueError with a message for the user."""
        if self.start > self.end:
            raise ValueError("The start date is after the end date.")
        if (self.end - self.start).days >= MAX_RANGE_DAYS:
            raise ValueError(f"The date range can be at most {MAX_RANGE_DAYS} days.")
        if self.method is not None and self.method not in METHODS:
            raise ValueError(f"Unknown method '{self.method}'.")
        if self.status is not None and self.status not in STATUSES:
            raise ValueError(f"Unknown status '{self.status}'.")
        if self.op is not None and self.op not in OPS:
            raise ValueError(f"Unknown operation '{self.op}'.")
        if self.table is not None and not TABLE_NAME_RE.match(self.table):
            raise ValueError(f"Invalid table name '{self.table}'.")
        if (self.row_id is not None or self.op is not None) and self.table is None:
            raise ValueError("Select a table to filter by row id or operation.")

    def where(self, tz: tzinfo) -> tuple[str, list[Any]]:
        since = datetime.combine(self.start, time.min, tzinfo=tz)
        until = datetime.combine(self.end + timedelta(days=1), time.min, tzinfo=tz)
        clauses = ["ts IS NOT NULL", "ts::TIMESTAMPTZ >= ?", "ts::TIMESTAMPTZ < ?"]
        params: list[Any] = [since, until]

        if self.user_id is not None:
            clauses.append("user_id = ?")
            params.append(self.user_id)
        if self.method is not None:
            clauses.append("method = ?")
            params.append(self.method)
        if self.status == "ok":
            clauses.append("status_code < 400")
        elif self.status == "error":
            clauses.append("status_code >= 400")
        if self.route:
            clauses.append("(contains(lower(route), lower(?)) OR contains(lower(path), lower(?)))")
            params += [self.route, self.route]
        if self.ip:
            clauses.append("ip = ?")
            params.append(self.ip)
        if self.table is not None:
            clauses.append(
                """len(list_filter(changes, lambda c: c."table" = ?
                    AND (?::VARCHAR IS NULL OR c.op = ?)
                    AND (?::VARCHAR IS NULL OR list_contains(list_transform(c.ids, lambda i: trim(i::VARCHAR, '"')), ?))
                )) > 0"""
            )
            params += [self.table, self.op, self.op, self.row_id, self.row_id]
        if self.share:
            # unknown or expired tokens are logged without resource_id, the token is then only in the path
            clauses.append("(resource_id = ? OR contains(path, ?))")
            params += [self.share, self.share]

        return " AND ".join(clauses), params


def parse_filter(params: dict[str, str], today: date) -> AuditFilter:
    """The filter from query parameters, empty values are ignored. Raises ValueError with a message for the user.

    Without dates it covers the last `DEFAULT_DAYS` days; with only a start date, as long a range as allowed.
    """
    values = {k: v.strip() for k, v in params.items() if k in FILTERS and v.strip()}
    try:
        start = date.fromisoformat(values.pop("start")) if "start" in values else None
        if "end" in values:
            end = date.fromisoformat(values.pop("end"))
        elif start is not None:
            end = min(today, start + timedelta(days=MAX_RANGE_DAYS - 1))
        else:
            end = today
        if start is None:
            start = end - timedelta(days=DEFAULT_DAYS - 1)
        user_id = int(values.pop("user_id")) if "user_id" in values else None
    except ValueError as e:
        raise ValueError(f"Invalid filter: {e}")
    flt = AuditFilter(start=start, end=end, user_id=user_id, **values)  # type: ignore[arg-type]
    flt.validate()
    return flt


@dataclass
class Change:
    table: str
    op: str
    count: int
    ids: list[Any]
    fields: list[str]
    bulk: bool

    @property
    def more(self) -> int:
        """Changed rows whose ids were not logged (at most 100 are)."""
        return max(self.count - len(self.ids), 0)


@dataclass
class AuditEntry:
    ts: datetime
    user_id: int | None
    method: str | None
    path: str | None
    route: str | None
    status_code: int | None
    process_time: float | None
    resource_id: str | None
    metadata: dict[str, Any]
    changes: list[Change]
    query_params: dict[str, Any]
    ip: str | None
    agent: str | None

    @property
    def owner_id(self) -> int | None:
        """Owner of the share token, for share link access."""
        owner_id = self.metadata.get("owner_id")
        return owner_id if isinstance(owner_id, int) else None

    @property
    def details(self) -> list[tuple[str, str]]:
        """Everything else that was logged, as (label, value) for display."""
        items = []
        if self.resource_id:
            items.append(("Resource", self.resource_id))
        for key, value in self.metadata.items():
            items.append((key.replace("_", " ").capitalize(), value if isinstance(value, str) else json.dumps(value, default=str)))
        for key, value in self.query_params.items():
            items.append((f"?{key}", value if isinstance(value, str) else json.dumps(value, default=str)))
        if self.process_time is not None:
            items.append(("Duration", f"{self.process_time * 1000:.0f} ms"))
        if self.agent:
            items.append(("User agent", self.agent))
        return items


@dataclass
class AuditPage:
    entries: list[AuditEntry] = field(default_factory=list)
    total: int = 0
    page: int = 0
    per_page: int = 50

    @property
    def num_pages(self) -> int:
        return math.ceil(self.total / self.per_page)


def query(audit_folder: str, flt: AuditFilter, tz: tzinfo, page: int = 0, per_page: int = 50) -> AuditPage:
    """Audit lines matching `flt`, newest first."""
    result = AuditPage(page=page, per_page=per_page)
    # files are named by the server's local date; one extra day on each side covers timezone offsets
    files = audit_files(audit_folder, since=flt.start - timedelta(days=1), until=flt.end + timedelta(days=1))
    if not files:
        return result

    where, params = flt.where(tz)
    with duckdb.connect() as con:
        con.execute(f"CREATE TEMP TABLE hits AS SELECT * FROM {read_json_sql()} WHERE {where}", [files, *params])
        row = con.execute("SELECT count(*) FROM hits").fetchone()
        result.total = row[0] if row else 0
        rows = con.execute(
            f"SELECT ts::TIMESTAMPTZ, {', '.join(c for c in COLUMNS if c != 'ts')} FROM hits "
            "ORDER BY ts::TIMESTAMPTZ DESC LIMIT ? OFFSET ?",
            [per_page, page * per_page],
        ).fetchall()

    result.entries = [_entry(dict(zip(COLUMNS, r))) for r in rows]
    return result


def _json(value: str | None) -> Any:
    if value is None:
        return None
    try:
        return json.loads(value)
    except ValueError:
        return value


def _entry(row: dict[str, Any]) -> AuditEntry:
    metadata = _json(row.pop("metadata"))
    query_params = _json(row.pop("query_params"))
    changes = [
        Change(
            table=c["table"], op=c["op"], count=c["count"] or 0, ids=[_json(i) for i in c["ids"] or []],
            fields=c["fields"] or [], bulk=bool(c["bulk"]),
        )
        for c in row.pop("changes") or []
    ]
    return AuditEntry(
        **row, changes=changes,
        metadata=metadata if isinstance(metadata, dict) else {},
        query_params=query_params if isinstance(query_params, dict) else {},
    )
