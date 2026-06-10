from typing import Any, TypeVar, Sequence

import sqlalchemy as sa
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy import sql

from ..models.Base import Base

SAModelType = TypeVar("SAModelType", bound=Base)
ScalarType = TypeVar("ScalarType")
QueryOptions = sa.sql.base.ExecutableOption | Sequence[sa.sql.base.ExecutableOption] | None
ColumnOptions = sa.ColumnElement[Any] | InstrumentedAttribute[Any] | sa.Function[Any]
type OrderBy = sql.expression.UnaryExpression


def apply_settings(
    statement: sa.Select[tuple[SAModelType]],
    order_by: OrderBy | None = None,
    limit: int | None = None,
    options: QueryOptions | None = None,
    offset: int | None = None
) -> sa.Select[Any]:
    if order_by is not None:
        statement = statement.order_by(order_by)
    if offset is not None:
        statement = statement.offset(offset)
    if limit is not None:
        statement = statement.limit(limit)
    if options is not None:
        statement = statement.options(options) if isinstance(options, sa.sql.base.ExecutableOption) else statement.options(*options)
    return statement