import math
from typing import Optional, Callable

import sqlalchemy as sa
from sqlalchemy.sql.base import ExecutableOption
from sqlalchemy.orm import Query

from ... import models, PAGE_LIMIT
from ...categories import ProjectStatus, ProjectStatusEnum, AccessType, AccessTypeEnum
from .. import exceptions
from ..DBBlueprint import DBBlueprint


class ProjectBP(DBBlueprint):
    @classmethod
    def where(
        cls,
        query: Query,
        seq_request_id: int | None = None,
        experiment_id: int | None = None,
        group_id: int | None = None,
        status: Optional[ProjectStatusEnum] = None,
        status_in: Optional[list[ProjectStatusEnum]] = None,
        user_id: int | None = None,
        custom_query: Callable[[Query], Query] | None = None,
    ) -> Query:
        if user_id is not None:
            query = query.where(
                sa.or_(
                    sa.exists().where(
                        (models.links.UserAffiliation.user_id == user_id) &
                        (models.links.UserAffiliation.group_id == models.Project.group_id)
                    ),
                    models.Project.owner_id == user_id,
                )
            )

        if group_id is not None:
            query = query.where(
                models.Project.group_id == group_id
            )

        if seq_request_id is not None:
            query = query.where(
                sa.exists().where(
                    (models.Sample.project_id == models.Project.id) &
                    (models.links.SampleLibraryLink.sample_id == models.Sample.id) &
                    (models.Library.id == models.links.SampleLibraryLink.library_id) &
                    (models.Library.seq_request_id == seq_request_id)
                )
            )

        if experiment_id is not None:
            query = query.where(
                sa.exists().where(
                    (models.Sample.project_id == models.Project.id) &
                    (models.links.SampleLibraryLink.sample_id == models.Sample.id) &
                    (models.Library.id == models.links.SampleLibraryLink.library_id) &
                    (models.Library.experiment_id == experiment_id)
                )
            )

        if status is not None:
            query = query.where(models.Project.status_id == status.id)

        if status_in is not None:
            query = query.where(models.Project.status_id.in_([s.id for s in status_in]))

        if custom_query is not None:
            query = custom_query(query)

        return query

    @DBBlueprint.transaction
    def create(
        self,
        title: str, description: str, owner_id: int,
        identifier: str | None = None,
        group_id: int | None = None,
        status: ProjectStatusEnum = ProjectStatus.DRAFT,
        flush: bool = True
    ) -> models.Project:
        if group_id is not None:
            if self.db.session.get(models.Group, group_id) is None:
                raise exceptions.ElementDoesNotExist(f"Group with id {group_id} does not exist")

        project = models.Project(
            identifier=identifier,
            title=title.strip(),
            description=description.strip(),
            owner_id=owner_id,
            group_id=group_id,
            status_id=status.id,
        )

        self.db.session.add(project)
        
        if flush:
            self.db.flush()

        return project
    
    @DBBlueprint.transaction
    def get(self, key: int | str, options: ExecutableOption | None = None) -> models.Project | None:
        if isinstance(key, int):
            if options is not None:
                project = self.db.session.query(models.Project).options(options).filter(models.Project.id == key).first()
            else:
                project = self.db.session.get(models.Project, key)
        elif isinstance(key, str):
            query = self.db.session.query(models.Project)
            if options is not None:
                query = query.options(options)
            project = query.filter(models.Project.identifier == key).first()
        else:
            raise ValueError("Key must be an integer (id) or string (identifier)")

        return project
    
    @DBBlueprint.transaction
    def find(
        self,
        seq_request_id: int | None = None,
        experiment_id: int | None = None,
        group_id: int | None = None,
        status: Optional[ProjectStatusEnum] = None,
        status_in: Optional[list[ProjectStatusEnum]] = None,
        user_id: int | None = None,
        limit: int | None = PAGE_LIMIT, offset: int | None = None,
        sort_by: Optional[str] = None, descending: bool = False,
        count_pages: bool = False,
        custom_query: Callable[[Query], Query] | None = None,
        options: ExecutableOption | None = None,
    ) -> tuple[list[models.Project], int | None]:
        query = self.db.session.query(models.Project)
        query = ProjectBP.where(
            query, seq_request_id=seq_request_id,
            group_id=group_id, status=status,
            status_in=status_in, user_id=user_id, experiment_id=experiment_id,
            custom_query=custom_query
        )

        if options is not None:
            query = query.options(options)

        if sort_by is not None:
            attr = getattr(models.Project, sort_by)

            if descending:
                attr = attr.desc()
            query = query.order_by(sa.nulls_last(attr))

        n_pages = None if not count_pages else math.ceil(query.count() / limit) if limit is not None else None

        if offset is not None:
            query = query.offset(offset)

        if limit is not None:
            query = query.limit(limit)

        projects = query.all()

        return projects, n_pages
    
    @DBBlueprint.transaction
    def delete(self, project_id: int, flush: bool = True):
        if (project := self.db.session.get(models.Project, project_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Project with id {project_id} does not exist")

        self.db.session.delete(project)

        if flush:
            self.db.flush()

    @DBBlueprint.transaction
    def update(self, project: models.Project):
        self.db.session.add(project)

    @DBBlueprint.transaction
    def query(
        self,
        identifier: str | None = None,
        title: str | None = None,
        identifier_title: str | None = None,
        seq_request_id: int | None = None,
        group_id: int | None = None,
        status: Optional[ProjectStatusEnum] = None,
        status_in: Optional[list[ProjectStatusEnum]] = None,
        user_id: int | None = None,
        limit: int | None = PAGE_LIMIT,
    ) -> list[models.Project]:
        query = self.db.session.query(models.Project)
        query = ProjectBP.where(
            query, seq_request_id=seq_request_id,
            group_id=group_id, status=status,
            status_in=status_in, user_id=user_id
        )
        
        if identifier is None and title is None and identifier_title is None:
            raise ValueError("Either identifier or title must be provided")
        if identifier is not None:
            query = query.order_by(sa.nulls_last(sa.func.similarity(models.Project.identifier, identifier).desc()))
        elif title is not None:
            query = query.order_by(sa.func.similarity(models.Project.title, title).desc())
        elif identifier_title is not None:
            query = query.order_by(
                sa.nulls_last(sa.func.greatest(
                    sa.func.similarity(models.Project.title, identifier_title),
                    sa.func.similarity(models.Project.identifier, identifier_title)
                ).desc())
            )
        if limit is not None:
            query = query.limit(limit)

        res = query.all()
        return res
    
    @DBBlueprint.transaction
    def get_access_type(self, project: models.Project, user: models.User) -> AccessTypeEnum:
        if user.is_admin():
            return AccessType.ADMIN
        if user.is_insider():
            return AccessType.INSIDER
        if project.owner_id == user.id:
            return AccessType.OWNER
        
        has_access: bool = self.db.session.query(
            sa.exists().where(
                (models.links.UserAffiliation.user_id == user.id) &
                (models.links.UserAffiliation.group_id == project.group_id)
            )
        ).scalar()

        if has_access:
            return AccessType.EDIT

        return AccessType.NONE

    @DBBlueprint.transaction
    def __getitem__(self, id: int | str) -> models.Project:
        if (project := self.get(id)) is None:
            raise exceptions.ElementDoesNotExist(f"Project with identifier '{id}' does not exist")
        return project