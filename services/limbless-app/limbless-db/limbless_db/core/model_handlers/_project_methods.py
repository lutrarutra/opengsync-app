import math
from typing import Optional, TYPE_CHECKING

import sqlalchemy as sa

if TYPE_CHECKING:
    from ..DBHandler import DBHandler
from ... import models, PAGE_LIMIT
from .. import exceptions


def create_project(self: "DBHandler", name: str, description: str, owner_id: int) -> models.Project:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (owner := self.session.get(models.User, owner_id)) is None:
        raise exceptions.ElementDoesNotExist(f"User with id {owner_id} does not exist")

    project = models.Project(
        name=name.strip(),
        description=description.strip(),
        owner_id=owner_id
    )

    self.session.add(project)
    owner.num_projects += 1

    self.session.commit()
    self.session.refresh(project)

    if not persist_session:
        self.close_session()
        
    return project


def get_project(self: "DBHandler", project_id: int) -> Optional[models.Project]:
    if not (persist_session := self._session is not None):
        self.open_session()

    res = self.session.get(models.Project, project_id)
    
    if not persist_session:
        self.close_session()
    return res


def get_projects(
    self: "DBHandler", limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,
    sort_by: Optional[str] = None, descending: bool = False,
    user_id: Optional[int] = None
) -> tuple[list[models.Project], int]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.Project)

    if user_id is not None:
        query = query.where(
            models.Project.owner_id == user_id
        )

    if sort_by is not None:
        attr = getattr(models.Project, sort_by)
        if descending:
            attr = attr.desc()
        query = query.order_by(attr)

    n_pages: int = math.ceil(query.count() / limit) if limit is not None else 1

    if offset is not None:
        query = query.offset(offset)

    if limit is not None:
        query = query.limit(limit)

    projects = query.all()

    if not persist_session:
        self.close_session()
    return projects, n_pages


def get_num_projects(self: "DBHandler", user_id: Optional[int] = None) -> int:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.Project)
    if user_id is not None:
        query = query.where(
            models.Project.owner_id == user_id
        )

    res = query.count()

    if not persist_session:
        self.close_session()
    return res


def delete_project(
    self: "DBHandler", project_id: int,
    commit: bool = True
) -> None:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (project := self.session.get(models.Project, project_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Project with id {project_id} does not exist")

    project.owner.num_projects -= 1
    self.session.delete(project)
    if commit:
        self.session.commit()

    if not persist_session:
        self.close_session()


def update_project(
    self: "DBHandler", project_id: int,
    name: Optional[str] = None,
    description: Optional[str] = None,
    commit: bool = True
) -> models.Project:
    if not (persist_session := self._session is not None):
        self.open_session()

    project = self.session.get(models.Project, project_id)
    if not project:
        raise exceptions.ElementDoesNotExist(f"Project with id {project_id} does not exist")

    if name is not None:
        project.name = name
    if description is not None:
        project.description = description

    if commit:
        self.session.commit()
        self.session.refresh(project)

    if not persist_session:
        self.close_session()
    return project


def project_contains_sample_with_name(
    self: "DBHandler", project_id: int, sample_name: str
) -> bool:
    if not (persist_session := self._session is not None):
        self.open_session()

    project = self.session.get(models.Project, project_id)
    if not project:
        raise exceptions.ElementDoesNotExist(f"Project with id {project_id} does not exist")

    res = self.session.query(models.Sample).where(
        models.Sample.name == sample_name
    ).where(
        models.Sample.project_id == project_id
    ).first() is not None

    if not persist_session:
        self.close_session()
    return res


def query_projects(
    self: "DBHandler", word: str,
    user_id: Optional[int] = None,
    limit: Optional[int] = PAGE_LIMIT,
) -> list[models.Project]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.Project)

    if user_id is not None:
        query = query.where(
            models.Project.owner_id == user_id
        )

    query = query.order_by(
        sa.func.similarity(models.Project.name, word).desc()
    )

    if limit is not None:
        query = query.limit(limit)

    res = query.all()

    if not persist_session:
        self.close_session()
    return res