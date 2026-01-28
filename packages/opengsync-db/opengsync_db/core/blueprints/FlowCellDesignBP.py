import math
from typing import Callable

import sqlalchemy as sa
from sqlalchemy.sql.base import ExecutableOption
from sqlalchemy.orm import Query

from ... import models, PAGE_LIMIT
from ...categories import TaskStatus, TaskStatusEnum, FlowCellTypeEnum
from .. import exceptions
from ..DBBlueprint import DBBlueprint


class FlowCellDesignBP(DBBlueprint):
    @classmethod
    def where(
        cls,
        query: Query,
        status: TaskStatusEnum | None = None,
        status_in: list[TaskStatusEnum] | None = None,
        archived: bool | None = None,
        custom_query: Callable[[Query], Query] | None = None
    ) -> Query:
        if status is not None:
            query = query.where(
                models.FlowCellDesign.task_status_id == status.id
            )

        if status_in is not None:
            query = query.where(
                models.FlowCellDesign.task_status_id.in_([status.id for status in status_in])
            )

        if archived is not None:
            if archived:
                query = query.where(
                    models.FlowCellDesign.task_status_id >= TaskStatus.COMPLETED.id
                )
            else:
                query = query.where(
                    models.FlowCellDesign.task_status_id < TaskStatus.COMPLETED.id
                )

        if custom_query is not None:
            query = custom_query(query)

        return query
    
    @DBBlueprint.transaction
    def create(
        self,
        name: str,
        task_status: TaskStatusEnum = TaskStatus.DRAFT,
        flow_cell_type: FlowCellTypeEnum | None = None,
        flush: bool = True
    ) -> models.FlowCellDesign:
        
        flow_cell_design = models.FlowCellDesign(
            name=name,
            task_status_id=task_status.id,
            flow_cell_type_id=flow_cell_type.id if flow_cell_type else None
        )

        self.db.session.add(flow_cell_design)
        
        if flush:
            self.db.flush()

        return flow_cell_design
    

    @DBBlueprint.transaction
    def get(self, id: int) -> models.FlowCellDesign | None:
        return self.db.session.get(models.FlowCellDesign, id)
    
    @DBBlueprint.transaction
    def find(
        self,
        status: TaskStatusEnum | None = None,
        status_in: list[TaskStatusEnum] | None = None,
        archived: bool | None = None,
        custom_query: Callable[[Query], Query] | None = None,
        limit: int | None = PAGE_LIMIT, offset: int | None = None,
        sort_by: str | None = None, descending: bool = False,
        page: int | None = None,
        options: ExecutableOption | None = None,
    ) -> tuple[list[models.FlowCellDesign], int | None]:
        
        query = self.db.session.query(models.FlowCellDesign)
        query = FlowCellDesignBP.where(
            query, status=status, status_in=status_in,
            archived=archived, custom_query=custom_query,
        )

        if options is not None:
            query = query.options(options)

        if sort_by is not None:
            attr = getattr(models.FlowCellDesign, sort_by)
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

        flow_cell_designs = query.all()

        return flow_cell_designs, n_pages
    
    @DBBlueprint.transaction
    def delete(self, flow_cell_design: models.FlowCellDesign, flush: bool = True):
        self.db.session.delete(flow_cell_design)

        if flush:
            self.db.flush()
        

    @DBBlueprint.transaction
    def update(self, flow_cell_design: models.FlowCellDesign):
        self.db.session.add(flow_cell_design)


    @DBBlueprint.transaction
    def __getitem__(self, id: int) -> models.FlowCellDesign:
        if (flow_cell_design := self.get(id)) is None:
            raise exceptions.ElementDoesNotExist(f"FlowCellDesign with id {id} does not exist")
        return flow_cell_design