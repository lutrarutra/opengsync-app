import math
from typing import Callable

import sqlalchemy as sa
from sqlalchemy.orm import Query

from ... import models, PAGE_LIMIT
from ...categories import (
    DataPathTypeEnum
)
from .. import exceptions
from ..DBBlueprint import DBBlueprint


class DataPathBP(DBBlueprint):
    @classmethod
    def where(
        cls,
        query: Query,
        type: DataPathTypeEnum | None = None,
        type_in: list[DataPathTypeEnum] | None = None,
        project_id: int | None = None,
        seq_request_id: int | None = None,
        library_id: int | None = None,
        experiment_id: int | None = None,
        custom_query: Callable[[Query], Query] | None = None,
    ) -> Query:
        if type is not None:
            query = query.filter(models.DataPath.type_id == type.id)

        if type_in is not None:
            query = query.filter(models.DataPath.type_id.in_([t.id for t in type_in]))

        if project_id is not None:
            query = query.filter(models.DataPath.project_id == project_id)

        if seq_request_id is not None:
            query = query.filter(models.DataPath.seq_request_id == seq_request_id)

        if library_id is not None:
            query = query.filter(models.DataPath.library_id == library_id)

        if experiment_id is not None:
            query = query.filter(models.DataPath.experiment_id == experiment_id)

        if custom_query is not None:
            query = custom_query(query)

        return query
        
    @DBBlueprint.transaction
    def create(
        self,
        path: str,
        type: DataPathTypeEnum,
        project: models.Project | None = None,
        seq_request: models.SeqRequest | None = None,
        library: models.Library | None = None,
        experiment: models.Experiment | None = None,
        flush: bool = True
    ) -> models.DataPath:
        
        data_path = models.DataPath(
            path=path,
            type_id=type.id,
            project=project,
            seq_request=seq_request,
            library=library,
            experiment=experiment,
        )

        self.db.session.add(data_path)
        if flush:
            self.db.flush()

        return data_path

    @DBBlueprint.transaction
    def get(self, id: int) -> models.DataPath | None:
        return self.db.session.get(models.DataPath, id)
    
    @DBBlueprint.transaction
    def find(
        self,
        type: DataPathTypeEnum | None = None,
        type_in: list[DataPathTypeEnum] | None = None,
        project_id: int | None = None,
        seq_request_id: int | None = None,
        library_id: int | None = None,
        experiment_id: int | None = None,
        limit: int | None = PAGE_LIMIT, offset: int | None = None,
        sort_by: str | None = None, descending: bool = False,
        count_pages: bool = False,
    ) -> tuple[list[models.DataPath], int | None]:
        
        query = self.db.session.query(models.DataPath)
        query = self.where(
            query,
            type=type,
            type_in=type_in,
            project_id=project_id,
            seq_request_id=seq_request_id,
            library_id=library_id,
            experiment_id=experiment_id,
        )

        if sort_by is not None:
            attr = getattr(models.DataPath, sort_by)
            if descending:
                attr = attr.desc()
            query = query.order_by(sa.nulls_last(attr))

        n_pages = None if not count_pages else math.ceil(query.count() / limit) if limit is not None else None

        if offset is not None:
            query = query.offset(offset)

        if limit is not None:
            query = query.limit(limit)

        seq_requests = query.all()

        return seq_requests, n_pages

    @DBBlueprint.transaction
    def delete(self, data_path: models.DataPath) -> None:
        self.db.session.delete(data_path)

    @DBBlueprint.transaction
    def update(self, data_path: models.DataPath):
        self.db.session.add(data_path)

    @DBBlueprint.transaction
    def __getitem__(self, id: int) -> models.DataPath:
        if (data_path := self.get(id)) is None:
            raise exceptions.ElementDoesNotExist(f"DataPath with id {id} not found")
        return data_path