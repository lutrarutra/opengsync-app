"""Values of free-text columns, picked with a ColumnValueInputField (components/inputs/column_value.py).

The values are not rows, so an option is identified by a normalized key of its value: values that differ only in
case or whitespace share a key and are offered once, with their most common spelling. New values whose key already
exists resolve to that spelling instead of adding a variant.

A source may be filtered by other values (department by institute): the filter value is normalized like the key it
is compared with.
"""
import hashlib
from dataclasses import dataclass, field
from typing import Any, Callable

import sqlalchemy as sa
from sqlalchemy import sql

from opengsync_db import SyncSession, models, utils

from . import responses
from .query_options import QUERY_PAGE_SIZE


def _collapse(value: str) -> str:
    return " ".join(value.split())


@dataclass(frozen=True)
class ColumnSource:
    # Normalized key of a value, the id of its option
    key: sql.ColumnElement[str]
    # Python counterpart of ``key``, for new values
    new_key: Callable[[tuple[str, ...]], str]
    # Searched and shown, in its most common spelling per key
    label: Any
    # Columns of a value (its most common spelling per key); the label column by default
    values: tuple[Any, ...] = ()
    # Cleans new values (whitespace collapsed by default)
    clean: Callable[[tuple[str, ...]], tuple[str, ...]] = lambda values: tuple(_collapse(v) for v in values)
    # Query parameter -> normalized key expression the parameter's value is compared with
    filters: dict[str, sql.ColumnElement[str]] = field(default_factory=dict)
    # Shown below the option name
    description: Any = None
    description_insiders_only: bool = False

    @property
    def value_columns(self) -> tuple[Any, ...]:
        return self.values or (self.label,)


def _md5(value: str) -> str:
    return hashlib.md5(value.encode()).hexdigest()


def _email_key(column: Any) -> sql.ColumnElement[str]:
    return sa.func.md5(sa.func.lower(sa.func.trim(column)))


SOURCES: dict[str, ColumnSource] = {
    "user_institute": ColumnSource(
        key=utils.norm_text(models.User.institute),
        new_key=lambda values: utils.norm_text_py(values[0]),
        label=models.User.institute,
    ),
    "user_department": ColumnSource(
        key=utils.norm_text(models.User.department),
        new_key=lambda values: utils.norm_text_py(values[0]),
        label=models.User.department,
        filters={"institute": utils.norm_text(models.User.institute)},
    ),
    # Keyed by the email (hashed, so the key does not reveal it); emails are shown to insiders only
    "user_pi": ColumnSource(
        key=_email_key(models.User.pi_email),
        new_key=lambda values: _md5(values[1].strip().lower()),
        label=models.User.pi_name,
        values=(models.User.pi_name, models.User.pi_email),
        clean=lambda values: (_collapse(values[0]), values[1].strip().lower()),
        description=models.User.pi_email,
        description_insiders_only=True,
    ),
}


def _most_common(column: Any) -> sql.ColumnElement[Any]:
    return sa.func.mode().within_group(column.asc())


def _grouped(source: ColumnSource, filters: dict[str, str | None] | None) -> sa.Select:
    """One row per key: key, its values, its description and the number of rows having it."""
    columns = [source.key.label("key"), *(_most_common(c).label(f"value_{i}") for i, c in enumerate(source.value_columns))]
    if source.description is not None:
        columns.append(_most_common(source.description).label("description"))
    stmt = sa.select(*columns, sa.func.count().label("n")).where(
        *(sa.func.trim(c) != "" for c in source.value_columns),
        *(c.is_not(None) for c in source.value_columns),
    )
    for name, value in (filters or {}).items():
        if value and (expression := source.filters.get(name)) is not None:
            stmt = stmt.where(expression == utils.norm_text_py(value))
    return stmt


def _values(row: Any, source: ColumnSource) -> tuple[str, ...]:
    return tuple(getattr(row, f"value_{i}") for i in range(len(source.value_columns)))


def search(
    session: SyncSession,
    source: ColumnSource,
    *,
    word: str | None,
    page: int,
    selected_id: str | None = None,
    filters: dict[str, str | None] | None = None,
    show_description: bool = True,
) -> tuple[list[responses.QueryOption], bool]:
    """A page of options: values containing ``word`` first, then similar ones (typos); the most used first."""
    stmt = _grouped(source, filters)
    if selected_id is not None and not word:
        stmt = stmt.where(source.key == selected_id)
    order: list[Any] = []
    if word:
        contains = utils.safe_ilike(source.label, word)
        stmt = stmt.where(sa.or_(contains, utils.safe_trgm_search(source.label, word)))
        order = [
            sa.func.max(sa.case((contains, 0), else_=1)).asc(),
            sa.func.max(sa.func.similarity(source.label, word)).desc(),
        ]
    stmt = stmt.group_by(source.key)

    count = session.scalar(sa.select(sa.func.count()).select_from(stmt.subquery())) or 0
    rows = session.execute(
        stmt.order_by(*order, sa.text("n DESC"), sa.text("value_0 ASC"))
        .limit(QUERY_PAGE_SIZE).offset(page * QUERY_PAGE_SIZE)
    ).all()

    options: list[responses.QueryOption] = []
    for row in rows:
        option: responses.QueryOption = {"id": row.key, "name": row.value_0}
        if show_description and source.description is not None and row.description:
            option["description"] = row.description
        options.append(option)
    return options, (page + 1) * QUERY_PAGE_SIZE < count


def lookup(
    session: SyncSession, source: ColumnSource, key: str, filters: dict[str, str | None] | None = None,
) -> tuple[str, ...] | None:
    """The values (most common spelling) of ``key``, or None if no row has it."""
    row = session.execute(_grouped(source, filters).where(source.key == key).group_by(source.key)).first()
    return _values(row, source) if row is not None else None


def resolve_new(
    session: SyncSession, source: ColumnSource, values: tuple[str, ...], filters: dict[str, str | None] | None = None,
) -> tuple[str, ...]:
    """The existing values with the key of the new ``values``, else the cleaned new values."""
    cleaned = source.clean(values)
    return lookup(session, source, source.new_key(cleaned), filters) or cleaned


def key_of(source: ColumnSource, values: tuple[str, ...]) -> str:
    """Key of stored ``values`` (to prefill a field)."""
    return source.new_key(source.clean(values))
