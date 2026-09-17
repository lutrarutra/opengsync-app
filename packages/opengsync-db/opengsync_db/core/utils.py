from typing import Any, TypeVar, Sequence

import sqlalchemy as sa
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy import sql

from ..models.Base import Base
from .EnumColumn import EnumColumn

SAModelType = TypeVar("SAModelType", bound=Base)
ScalarType = TypeVar("ScalarType")
QueryOptions = sa.sql.base.ExecutableOption | Sequence[sa.sql.base.ExecutableOption] | None
ColumnOptions = sa.ColumnElement[Any] | InstrumentedAttribute[Any] | sa.Function[Any]
type OrderBy = sql.expression.UnaryExpression


def prepare_pandas_statement(statement: sa.Select) -> tuple[sa.Select, list[sa.ColumnElement[Any]]]:
    """Label mapped columns with their Python keys before reading into pandas."""
    selected_columns: list[sa.ColumnElement[Any]] = []
    for column in statement.selected_columns:
        key = getattr(column, "key", None)
        name = getattr(column, "name", None)
        selected_columns.append(
            column.label(key) if key is not None and key != name else column
        )
    return (
        statement.with_only_columns(*selected_columns, maintain_column_froms=True),
        selected_columns,
    )


def map_pandas_enum_columns(dataframe: Any, columns: list[sa.ColumnElement[Any]]) -> Any:
    """Apply EnumColumn result conversion to DataFrame columns."""
    for column in columns:
        if isinstance(column.type, EnumColumn):
            name = getattr(column, "name", None)
            if name is not None and name in dataframe:
                dataframe[name] = column.type.enum_class.map_series(dataframe[name])
    return dataframe


def safe_ilike(
    column: sql.ColumnElement | InstrumentedAttribute, value: str,
) -> sql.ColumnElement[bool]:
    """ILIKE with SQL wildcard characters escaped (exact substring match)."""
    safe = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return column.ilike(f"%{safe}%", escape="\\")


def safe_trgm_search(
    column: sql.ColumnElement | InstrumentedAttribute, value: str, threshold: float = 0.05,
) -> sql.ColumnElement[bool]:
    """Trigram similarity search allowing typos.
    
    Uses pg_trgm similarity() with a configurable threshold.
    Default threshold of 0.05 allows moderate typos while avoiding noise.
    """
    return sa.func.similarity(column, value) > threshold


def apply_settings(
    statement: sa.Select[tuple[SAModelType]],
    order_by: OrderBy | None = None,
    limit: int | None = None,
    options: QueryOptions | None = None,
    offset: int | None = None
) -> sa.Select[Any]:
    if order_by is not None:
        statement = statement.order_by(sa.nulls_last(order_by))
    if offset is not None:
        statement = statement.offset(offset)
    if limit is not None:
        statement = statement.limit(limit)
    if options is not None:
        statement = statement.options(options) if isinstance(options, sa.sql.base.ExecutableOption) else statement.options(*options)
    return statement