import math
from typing import Callable

import sqlalchemy as sa
from sqlalchemy.sql.base import ExecutableOption
from sqlalchemy.orm import Query

from ... import models, PAGE_LIMIT
from ...categories import TaskStatus
from .. import exceptions
from ..DBBlueprint import DBBlueprint


class PoolDesignBP(DBBlueprint):
    @classmethod
    def where(
        cls,
        query: Query,
        flow_cell_design_id: int | None = None,
        orphan: bool | None = None,
        archived: bool | None = None,
        custom_query: Callable[[Query], Query] | None = None
    ) -> Query:
        if flow_cell_design_id is not None:
            query = query.where(
                models.PoolDesign.flow_cell_design_id == flow_cell_design_id
            )

        if orphan is not None:
            if orphan:
                query = query.where(
                    models.PoolDesign.flow_cell_design_id.is_(None)
                )
            else:
                query = query.where(
                    models.PoolDesign.flow_cell_design_id.is_not(None)
                )

        if archived is not None:
            if archived:
                query = query.where(
                    sa.exists(
                        models.PoolDesign.flow_cell_design_id == models.FlowCellDesign.id &
                        models.FlowCellDesign.task_status_id >= TaskStatus.COMPLETED.id
                    )
                )
            else:
                query = query.where(
                    sa.exists(
                        models.PoolDesign.flow_cell_design_id == models.FlowCellDesign.id &
                        models.FlowCellDesign.task_status_id < TaskStatus.COMPLETED.id
                    )
                )

        if custom_query is not None:
            query = custom_query(query)

        return query
    
    @DBBlueprint.transaction
    def create(
        self,
        name: str,
        cycles_r1: int,
        cycles_i1: int,
        cycles_i2: int,
        cycles_r2: int,
        num_m_requested_reads: float | None,
        flush: bool = True
    ) -> models.PoolDesign:
        pool_design = models.PoolDesign(
            name=name,
            num_m_requested_reads=num_m_requested_reads,
            cycles_r1=cycles_r1,
            cycles_i1=cycles_i1,
            cycles_r2=cycles_r2,
            cycles_i2=cycles_i2,
        )

        self.db.session.add(pool_design)

        if flush:
            self.db.flush()

        return pool_design
    
    @DBBlueprint.transaction
    def get(self, id: int) -> models.PoolDesign | None:
        return self.db.session.get(models.PoolDesign, id)
    
    @DBBlueprint.transaction
    def find(
        self,
        flow_cell_design_id: int | None = None,
        archived: bool | None = None,
        orphan: bool | None = None,
        custom_query: Callable[[Query], Query] | None = None,
        limit: int | None = PAGE_LIMIT, offset: int | None = None,
        sort_by: str | None = None, descending: bool = False,
        page: int | None = None,
        options: ExecutableOption | None = None,
    ) -> tuple[list[models.PoolDesign], int | None]:
        
        query = self.db.session.query(models.PoolDesign)
        query = PoolDesignBP.where(
            query, archived=archived, flow_cell_design_id=flow_cell_design_id,
            custom_query=custom_query, orphan=orphan
        )

        if options is not None:
            query = query.options(options)

        if sort_by is not None:
            attr = getattr(models.PoolDesign, sort_by)
            if descending:
                attr = attr.desc()
            query = query.order_by(sa.nulls_last(attr))

        if page is not None:
            if limit is None:
                raise ValueError("Limit must be provided when page is provided")
            
            count = query.count()
            n_pages = math.ceil(count / limit)
            query = query.offset(min(page, max(0, n_pages - 1)) * limit)
        else:
            n_pages = None

        if offset is not None:
            query = query.offset(offset)

        if limit is not None:
            query = query.limit(limit)

        pool_designs = query.all()

        return pool_designs, n_pages

    @DBBlueprint.transaction
    def delete(self, pool_design: models.PoolDesign, flush: bool = True):
        self.db.session.delete(pool_design)

        if flush:
            self.db.flush()


    @DBBlueprint.transaction
    def update(self, pool_design: models.PoolDesign):
        self.db.session.add(pool_design)

    @DBBlueprint.transaction
    def __getitem__(self, id: int) -> models.PoolDesign:
        if (pool_design := self.get(id)) is None:
            raise exceptions.ElementDoesNotExist(f"PoolDesign with ID {id} does not exist")
        return pool_design