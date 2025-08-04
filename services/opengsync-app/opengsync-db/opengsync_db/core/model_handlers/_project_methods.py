import math
from typing import Optional, TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Query
from sqlalchemy import or_

if TYPE_CHECKING:
    from ..DBHandler import DBHandler
from ... import models, PAGE_LIMIT
from ...categories import ProjectStatus, ProjectStatusEnum
from .. import exceptions


def create_project(
    self: "DBHandler",
    title: str, description: str, owner_id: int,
    identifier: str | None = None,
    group_id: int | None = None,
    status: ProjectStatusEnum = ProjectStatus.DRAFT,
    flush: bool = True
) -> models.Project:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (owner := self.session.get(models.User, owner_id)) is None:
        raise exceptions.ElementDoesNotExist(f"User with id {owner_id} does not exist")
    
    if group_id is not None:
        if self.session.get(models.Group, group_id) is not None:
            raise exceptions.ElementDoesNotExist(f"Group with id {group_id} does not exist")

    project = models.Project(
        identifier=identifier,
        title=title.strip(),
        description=description.strip(),
        owner_id=owner_id,
        group_id=group_id,
        status_id=status.id,
    )

    owner.num_projects += 1
    self.session.add(project)
    
    if flush:
        self.session.flush()

    if not persist_session:
        self.close_session()
        
    return project


def get_project(self: "DBHandler", project_id: int | None = None, identifier: str | None = None) -> models.Project | None:
    if not (persist_session := self._session is not None):
        self.open_session()

    if project_id is None and identifier is None:
        raise ValueError("Either project_id or identifier must be provided")
    
    if project_id is not None:
        res = self.session.get(models.Project, project_id)
    else:
        res = self.session.query(models.Project).filter(
            models.Project.identifier == identifier
        ).first()
    
    if not persist_session:
        self.close_session()
    return res


def where(
    query: Query,
    seq_request_id: Optional[int] = None,
    group_id: Optional[int] = None,
    status: Optional[ProjectStatusEnum] = None,
    status_in: Optional[list[ProjectStatusEnum]] = None,
    user_id: Optional[int] = None,
) -> Query:
    
    if user_id is not None:
        query = query.join(
            models.links.UserAffiliation,
            models.links.UserAffiliation.group_id == models.Project.group_id,
            isouter=True
        ).where(
            or_(
                models.links.UserAffiliation.user_id == user_id,
                models.Project.owner_id == user_id,
            )
        ).distinct(models.Project.id)

    if group_id is not None:
        query = query.where(
            models.Project.group_id == group_id
        )

    if seq_request_id is not None:
        query = query.join(
            models.Sample,
            models.Sample.project_id == models.Project.id,
        ).join(
            models.links.SampleLibraryLink,
            models.links.SampleLibraryLink.sample_id == models.Sample.id,
        ).join(
            models.Library,
            models.Library.id == models.links.SampleLibraryLink.library_id,
        ).where(
            models.Library.seq_request_id == seq_request_id
        ).distinct(models.Project.id)

    if status is not None:
        query = query.where(models.Project.status_id == status.id)

    if status_in is not None:
        query = query.where(models.Project.status_id.in_([s.id for s in status_in]))

    return query


def get_projects(
    self: "DBHandler",
    seq_request_id: Optional[int] = None,
    group_id: Optional[int] = None,
    status: Optional[ProjectStatusEnum] = None,
    status_in: Optional[list[ProjectStatusEnum]] = None,
    user_id: Optional[int] = None,
    limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
    sort_by: Optional[str] = None, descending: bool = False,
    count_pages: bool = False,
) -> tuple[list[models.Project], int | None]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.Project)
    query = where(
        query, seq_request_id=seq_request_id,
        group_id=group_id, status=status,
        status_in=status_in, user_id=user_id
    )

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

    if not persist_session:
        self.close_session()
    return projects, n_pages


def delete_project(self: "DBHandler", project_id: int, flush: bool = True):
    if not (persist_session := self._session is not None):
        self.open_session()

    if (project := self.session.get(models.Project, project_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Project with id {project_id} does not exist")

    project.owner.num_projects -= 1
    self.session.delete(project)

    if flush:
        self.session.flush()

    if not persist_session:
        self.close_session()


def update_project(self: "DBHandler", project: models.Project) -> models.Project:
    if not (persist_session := self._session is not None):
        self.open_session()

    self.session.add(project)

    if not persist_session:
        self.close_session()
    return project


def query_projects(
    self: "DBHandler",
    identifier: str | None = None,
    title: str | None = None,
    identifier_title: str | None = None,
    seq_request_id: Optional[int] = None,
    group_id: Optional[int] = None,
    status: Optional[ProjectStatusEnum] = None,
    status_in: Optional[list[ProjectStatusEnum]] = None,
    user_id: Optional[int] = None,
    limit: Optional[int] = PAGE_LIMIT,
) -> list[models.Project]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.Project)
    query = where(
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

    if not persist_session:
        self.close_session()
    return res