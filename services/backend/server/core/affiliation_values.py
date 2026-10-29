"""Institutes, departments and PIs of users, listed and edited by admins (admin Affiliations page).

They are free-text user columns (core/column_values.py), so a value is the set of users whose column has its key:
editing a value rewrites those users, merging it gives them the values of another key. A department is scoped to
its institute: the same department name at two institutes is two values.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Any, Sequence

import sqlalchemy as sa
from sqlalchemy import sql

from opengsync_db import SyncSession, models, utils

from . import column_values


class Kind(str, Enum):
    INSTITUTE = "institute"
    DEPARTMENT = "department"
    PI = "pi"

    @property
    def source(self) -> column_values.ColumnSource:
        return column_values.SOURCES[_SOURCES[self]]

    @property
    def source_name(self) -> str:
        return _SOURCES[self]

    @property
    def label(self) -> str:
        return _LABELS[self][0]

    @property
    def plural(self) -> str:
        return _LABELS[self][1]


_SOURCES = {Kind.INSTITUTE: "user_institute", Kind.DEPARTMENT: "user_department", Kind.PI: "user_pi"}
_LABELS = {Kind.INSTITUTE: ("Institute", "Institutes"), Kind.DEPARTMENT: ("Department", "Departments"), Kind.PI: ("PI", "PIs")}

# Institute key a department is scoped to; empty for departments of users without an institute
_INSTITUTE_KEY = utils.norm_text(sa.func.coalesce(models.User.institute, ""))

SORT_COLUMNS = ("name", "num_users")


@dataclass
class Value:
    key: str
    name: str
    num_users: int
    # Distinct spellings (case, whitespace) stored for the key
    num_spellings: int
    # PI only
    email: str | None = None
    # Department only
    institute_key: str | None = None
    institute: str | None = None

    @property
    def params(self) -> dict[str, str]:
        """Query parameters identifying the value (``key``, plus ``institute`` for departments)."""
        params = {"key": self.key}
        if self.institute_key is not None:
            params["institute"] = self.institute_key
        return params


def _most_common(column: Any) -> sql.ColumnElement[Any]:
    return sa.func.mode().within_group(column.asc())


def users_of(kind: Kind, key: str, institute_key: str | None = None) -> sql.ColumnElement[bool]:
    """Users having the value ``key`` (of the institute ``institute_key`` for departments)."""
    where = kind.source.key == key
    if kind == Kind.DEPARTMENT:
        where = sa.and_(where, _INSTITUTE_KEY == (institute_key or ""))
    return where


def _grouped(kind: Kind) -> sa.Select:
    source = kind.source
    columns = source.value_columns
    selected = [
        source.key.label("key"),
        _most_common(columns[0]).label("name"),
        sa.func.count().label("num_users"),
        sa.func.count(sa.distinct(sa.func.concat_ws("\x1f", *columns))).label("num_spellings"),
    ]
    group_by: list[Any] = [source.key]
    if kind == Kind.PI:
        selected.append(_most_common(columns[1]).label("email"))
    if kind == Kind.DEPARTMENT:
        selected += [_INSTITUTE_KEY.label("institute_key"), _most_common(models.User.institute).label("institute")]
        group_by.append(_INSTITUTE_KEY)
    return sa.select(*selected).where(
        *(c.is_not(None) for c in columns), *(sa.func.trim(c) != "" for c in columns),
    ).group_by(*group_by)


def _value(kind: Kind, row: Any) -> Value:
    return Value(
        key=row.key, name=row.name, num_users=row.num_users, num_spellings=row.num_spellings,
        email=row.email if kind == Kind.PI else None,
        institute_key=row.institute_key if kind == Kind.DEPARTMENT else None,
        institute=row.institute if kind == Kind.DEPARTMENT else None,
    )


def listing(
    session: SyncSession, kind: Kind, *,
    name: str | None = None, email: str | None = None,
    sort: str = "num_users", descending: bool = True, page: int = 0, limit: int = 10,
) -> tuple[list[Value], int]:
    """A page of values and the number of all values matching the searches."""
    stmt = _grouped(kind)
    if name:
        stmt = stmt.where(utils.safe_ilike(kind.source.label, name))
    if email and kind == Kind.PI:
        stmt = stmt.where(utils.safe_ilike(models.User.pi_email, email))

    count = session.scalar(sa.select(sa.func.count()).select_from(stmt.subquery())) or 0
    order = sa.column(sort).desc() if descending else sa.column(sort).asc()
    rows = session.execute(
        stmt.order_by(order, sa.column("name").asc(), sa.column("key").asc()).limit(limit).offset(page * limit)
    ).all()
    return [_value(kind, row) for row in rows], count


def get(session: SyncSession, kind: Kind, key: str, institute_key: str | None = None) -> Value | None:
    row = session.execute(_grouped(kind).where(users_of(kind, key, institute_key))).first()
    return _value(kind, row) if row is not None else None


def users(session: SyncSession, value: Value, kind: Kind, limit: int = 20) -> Sequence[models.User]:
    """Some users having ``value``, by name."""
    return session.scalars(
        sa.select(models.User).where(users_of(kind, value.key, value.institute_key))
        .order_by(models.User.last_name, models.User.first_name, models.User.id).limit(limit)
    ).all()


def account_of_pi(session: SyncSession, email: str | None) -> models.User | None:
    """The user whose own email is the PI email (the PI has an account)."""
    if not email:
        return None
    return session.scalars(
        sa.select(models.User).where(sa.func.lower(models.User.email) == email.strip().lower()).limit(1)
    ).first()


def pi_accounts(session: SyncSession, values: list[Value]) -> dict[str, models.User]:
    """Accounts of the PIs among ``values``, by value key."""
    emails = {value.email.strip().lower(): value.key for value in values if value.email}
    if not emails:
        return {}
    accounts = session.scalars(sa.select(models.User).where(sa.func.lower(models.User.email).in_(emails))).all()
    return {emails[user.email.lower()]: user for user in accounts}


def assign(session: SyncSession, kind: Kind, value: Value, values: tuple[str, ...]) -> int:
    """Store ``values`` (name, plus email for PIs) on every user having ``value``; the number of users changed."""
    columns = [c.key for c in kind.source.value_columns]
    result = session.execute(
        sa.update(models.User).where(users_of(kind, value.key, value.institute_key))
        .values(dict(zip(columns, values))).execution_options(synchronize_session="fetch")
    )
    return result.rowcount  # type: ignore[attr-defined]
