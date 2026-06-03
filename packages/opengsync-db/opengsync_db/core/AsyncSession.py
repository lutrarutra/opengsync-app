from typing import Any, Sequence, AsyncIterator

from pydantic import BaseModel
import sqlalchemy as sa
from sqlalchemy import exc as sa_exc
from sqlalchemy import sql
from sqlalchemy.ext.asyncio import AsyncSession as SQLAlchemyAsyncSession

from . import utils
from .exceptions import ModelNotFoundException

class AsyncSession(SQLAlchemyAsyncSession):
    async def get_all(
        self,
        statement: sa.Select[tuple[utils.SAModelType]],
        order_by: sql.expression.UnaryExpression | None = None,
        limit: int | None = 10,
        options: utils.QueryOptions | None = None,
        offset: int | None = None
    ) -> Sequence[utils.SAModelType]:
        """Execute a select statement and return a sequence of objects."""
        statement = utils.apply_settings(statement, order_by=order_by, limit=limit, options=options, offset=offset)
        result = await super().execute(statement)
        return result.scalars().all()
    
    async def page(
        self,
        statement: sa.Select[tuple[utils.SAModelType]],
        page: int,
        order_by: sql.expression.UnaryExpression | None = None,
        limit: int = 10,
        options: utils.QueryOptions | None = None
    ) -> tuple[Sequence[utils.SAModelType], int]:
        """Execute a select statement and return a page of objects."""
        count = await self.count(statement)
        offset = page * limit
        
        if offset >= count:
            return [], count

        return await self.get_all(statement, limit=limit, offset=offset, order_by=order_by, options=options), count

    async def first(self, statement: sa.Select[tuple[utils.SAModelType]], options: utils.QueryOptions = None) -> utils.SAModelType | None:
        """Execute a select statement and return a single object or None."""
        statement = utils.apply_settings(statement, options=options)
        result = await super().execute(statement.limit(1))
        return result.scalar()
    
    async def exists(self, statement: sa.Select[tuple[utils.SAModelType]]) -> bool:
        """Execute a select statement and return True if any rows exist."""
        result = await super().execute(sa.select(sql.exists(statement)))
        return result.scalar() or False
    
    async def first_or_fail(self, statement: sa.Select[tuple[utils.SAModelType]], options: utils.QueryOptions = None) -> utils.SAModelType:
        """Execute a select statement and return a single object or raise ObjectNotFound."""
        statement = utils.apply_settings(statement, options=options)
        result = await super().execute(statement.limit(1))
        if (obj := result.scalar()) is None:
            entity = statement.column_descriptions[0].get("entity")
            model_name = entity.__name__ if entity else "Item"
            raise ModelNotFoundException(f"{model_name} not found")
        return obj
    
    async def get_one(self, statement: sa.Select[tuple[utils.SAModelType]], options: utils.QueryOptions = None) -> utils.SAModelType:
        """
        Execute a select statement and return exactly one object.
        Raises ModelNotFoundException if no results or multiple results are found.
        """
        statement = utils.apply_settings(statement, options=options)
        result = await super().execute(statement)
        
        try:
            return result.scalars().one()
        except (sa_exc.NoResultFound, sa_exc.MultipleResultsFound) as e:
            entity = statement.column_descriptions[0].get("entity")
            model_name = entity.__name__ if entity else "Item"
            
            error_msg = f"{model_name} not found" 
            if isinstance(e, sa_exc.MultipleResultsFound):
                error_msg = f"Multiple {model_name} found, expected only one"
                
            raise ModelNotFoundException(error_msg)
    
    async def get_access_level(self, statement: sa.Select[tuple[utils.ScalarType]]) -> utils.ScalarType:
        """Execute a select statement and return a single scalar value."""
        result = await super().execute(statement)
        if (obj := result.scalar_one_or_none()) is None:
            entity = statement.column_descriptions[0].get("entity")
            model_name = entity.__name__ if entity else "Item"
            raise ModelNotFoundException(f"{model_name} not found")
        return obj

    async def count(self, statement: sa.Select[tuple[utils.SAModelType]]) -> int:
        """Execute a count statement and return the integer."""
        result = await super().execute(sa.select(sa.func.count()).select_from(statement.order_by(None).subquery()))
        return result.scalar_one() or 0

    async def save(self, model: utils.SAModelType, flush: bool = False) -> utils.SAModelType:
        """Add a model to the session and optionally commit."""
        self.add(model)
        if flush:
            await self.flush()
        return model
    
    async def delete(self, model: Any, flush: bool = False) -> None:
        """Delete a model from the session and optionally commit."""
        await super().delete(model)
        if flush:
            await self.flush()

    async def __getitem__(self, statement: sa.Select[tuple[utils.SAModelType]]) -> utils.SAModelType:
        return await self.first_or_fail(statement)
    
    async def iter(
        self, statement: sa.Select[tuple[utils.SAModelType]],
        order_by: sql.expression.UnaryExpression | None = None,
        batch_size: int = 100,
        options: utils.QueryOptions | None = None
    ) -> AsyncIterator[utils.SAModelType]:
        """Execute a select statement and return an async iterator of objects."""
        statement = utils.apply_settings(statement, options=options, order_by=order_by)
        statement = statement.execution_options(stream_results=True)
        result = await super().stream(statement)
        return result.scalars().yield_per(batch_size)