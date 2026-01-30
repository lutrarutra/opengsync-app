import math
from typing import Callable

import sqlalchemy as sa
from sqlalchemy.orm import Query
from sqlalchemy.sql.base import ExecutableOption

from ... import models, PAGE_LIMIT
from ...categories import (
    DataPathType
)
from .. import exceptions
from ..DBBlueprint import DBBlueprint


class DataPathBP(DBBlueprint):
    @classmethod
    def where(
        cls,
        query: Query,
        path: str | None = None,
        type: DataPathType | None = None,
        type_in: list[DataPathType] | None = None,
        project_id: int | None = None,
        seq_request_id: int | None = None,
        library_id: int | None = None,
        experiment_id: int | None = None,
        custom_query: Callable[[Query], Query] | None = None,
    ) -> Query:
        if path is not None:
            query = query.filter(models.DataPath.path == path)

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
        type: DataPathType,
        project: models.Project | None = None,
        seq_request: models.SeqRequest | None = None,
        library: models.Library | None = None,
        experiment: models.Experiment | None = None,
        flush: bool = True
    ) -> models.DataPath:
        
        query = self.db.session.query(models.DataPath).filter(models.DataPath.path == path)

        if project is not None:
            if query.filter(models.DataPath.project_id == project.id).first() is not None:
                raise exceptions.LinkAlreadyExists(f"DataPath with path '{path}' already linked to project with id '{project.id}'")
        if seq_request is not None:
            if query.filter(models.DataPath.seq_request_id == seq_request.id).first() is not None:
                raise exceptions.LinkAlreadyExists(f"DataPath with path '{path}' already linked to seq_request with id '{seq_request.id}'")
        if library is not None:
            if query.filter(models.DataPath.library_id == library.id).first() is not None:
                raise exceptions.LinkAlreadyExists(f"DataPath with path '{path}' already linked to library with id '{library.id}'")
        if experiment is not None:
            if query.filter(models.DataPath.experiment_id == experiment.id).first() is not None:
                raise exceptions.LinkAlreadyExists(f"DataPath with path '{path}' already linked to experiment with id '{experiment.id}'")

        
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
    def get(self, id: int, options: ExecutableOption | None = None) -> models.DataPath | None:
        if options is not None:
            return self.db.session.query(models.DataPath).options(options).filter(models.DataPath.id == id).first()
        else:
            return self.db.session.get(models.DataPath, id)
    
    @DBBlueprint.transaction
    def find(
        self,
        path: str | None = None,
        type: DataPathType | None = None,
        type_in: list[DataPathType] | None = None,
        project_id: int | None = None,
        seq_request_id: int | None = None,
        library_id: int | None = None,
        experiment_id: int | None = None,
        sort_by: str | None = None, descending: bool = False,
        limit: int | None = PAGE_LIMIT, offset: int | None = None,
        page: int | None = None,
        custom_query: Callable[[Query], Query] | None = None,
        options: ExecutableOption | None = None,
    ) -> tuple[list[models.DataPath], int | None]:
        
        query = self.db.session.query(models.DataPath)
        query = self.where(
            query,
            path=path,
            type=type,
            type_in=type_in,
            project_id=project_id,
            experiment_id=experiment_id,
            seq_request_id=seq_request_id,
            library_id=library_id,
            custom_query=custom_query
        )
        if options is not None:
            query = query.options(options)

        if sort_by is not None:
            attr = getattr(models.DataPath, sort_by)
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