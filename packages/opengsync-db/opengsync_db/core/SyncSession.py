from typing import Sequence, Iterator

import sqlalchemy as sa
from sqlalchemy import sql
from sqlalchemy.orm import Session as SQLAlchemySession

from . import utils
from .exceptions import ModelNotFoundException

class _DefaultLimitSentinel(int):
    pass

DEFAULT_LIMIT = _DefaultLimitSentinel()

class SyncSession(SQLAlchemySession):
    def __init__(self, *args, default_limit: int, **kwargs):
        self.default_limit = default_limit
        super().__init__(*args, **kwargs)

    def get_all(
        self,
        statement: sa.Select[tuple[utils.SAModelType]],
        order_by: sql.expression.UnaryExpression | None = None,
        limit: int | None = DEFAULT_LIMIT,
        options: utils.QueryOptions | None = None,
        offset: int | None = None
    ) -> Sequence[utils.SAModelType]:
        """Execute a select statement and return a sequence of objects."""
        if limit is DEFAULT_LIMIT:
            limit = self.default_limit
        statement = utils.apply_settings(statement, order_by=order_by, limit=limit, options=options, offset=offset)
        result = super().execute(statement)
        return result.scalars().all()
    
    def page(
        self,
        statement: sa.Select[tuple[utils.SAModelType]],
        page: int,
        order_by: sql.expression.UnaryExpression | None = None,
        limit: int = 10,
        options: utils.QueryOptions | None = None
    ) -> tuple[Sequence[utils.SAModelType], int]:
        """Execute a select statement and return a page of objects."""
        count = self.count(statement)
        offset = page * limit
        
        if offset >= count:
            return [], count

        return self.get_all(statement, limit=limit, offset=offset, order_by=order_by, options=options), count

    def first(self, statement: sa.Select[tuple[utils.SAModelType]], options: utils.QueryOptions = None) -> utils.SAModelType | None:
        """Execute a select statement and return a single object or None."""
        statement = utils.apply_settings(statement, options=options)
        result = super().execute(statement.limit(1))
        return result.scalar_one_or_none()
    
    def exists(self, statement: sa.Select[tuple[utils.SAModelType]]) -> bool:
        """Execute a select statement and return True if any rows exist."""
        result = super().execute(sa.select(sql.exists(statement)))
        return result.scalar() or False
    
    def get_one(self, statement: sa.Select[tuple[utils.SAModelType]], options: utils.QueryOptions = None) -> utils.SAModelType:
        """Execute a select statement and return a single object or raise ModelNotFoundException."""
        statement = utils.apply_settings(statement, options=options)
        result = super().execute(statement)
        if (obj := result.scalar_one_or_none()) is None:
            entity = statement.column_descriptions[0].get("entity")
            model_name = entity.__name__ if entity else "Item"
            raise ModelNotFoundException(f"{model_name} not found")
        return obj
    
    def get_access_level(self, statement: sa.Select[tuple[utils.ScalarType]]) -> utils.ScalarType:
        """Execute a select statement and return a single scalar value."""
        result = super().execute(statement)
        if (obj := result.scalar_one_or_none()) is None:
            entity = statement.column_descriptions[0].get("entity")
            model_name = entity.__name__ if entity else "Item"
            raise ModelNotFoundException(f"{model_name} not found")
        return obj

    def count(self, statement: sa.Select[tuple[utils.SAModelType]]) -> int:
        """Execute a count statement and return the integer."""
        result = super().execute(sa.select(sa.func.count()).select_from(statement.order_by(None).subquery()))
        return result.scalar_one() or 0

    def save(self, model: utils.SAModelType, flush: bool = False) -> utils.SAModelType:
        """Add a model to the session and optionally flush."""
        self.add(model)
        if flush:
            self.flush()
        return model
    
    def delete(self, model: utils.Base, flush: bool = False) -> None:
        """Delete a model from the session and optionally flush."""
        super().delete(model)
        if flush:
            self.flush()

    def __getitem__(self, statement: sa.Select[tuple[utils.SAModelType]]) -> utils.SAModelType:
        return self.get_one(statement)
    
    def iter(
        self, statement: sa.Select[tuple[utils.SAModelType]],
        order_by: sql.expression.UnaryExpression | None = None,
        batch_size: int = 100,
        options: utils.QueryOptions | None = None
    ) -> Iterator[utils.SAModelType]:
        """Execute a select statement and return an iterator of objects."""
        statement = utils.apply_settings(statement, options=options, order_by=order_by)
        statement = statement.execution_options(yield_per=batch_size)
        result = super().execute(statement)
        return result.scalars()