from typing import Optional, Union

from ... import models
from .. import exceptions


def create_project(self, name: str, description: str, commit: bool = True) -> models.Project:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if self._session.query(models.Project).where(
        models.Project.name == name
    ).first() is not None:
        raise exceptions.NotUniqueValue(f"Project with name {name} already exists")

    project = models.Project(
        name=name,
        description=description
    )

    self._session.add(project)
    if commit:
        self._session.commit()
    self._session.refresh(project)

    if not persist_session:
        self.close_session()
    return project


def get_project(self, project_id: int) -> models.Project:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.get(models.Project, project_id)
    if not persist_session:
        self.close_session()
    return res


def get_projects(self, limit: Optional[int] = 20, offset: Optional[int] = None) -> list[models.Project]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.Project).order_by(models.Project.id.desc())
    if offset is not None:
        query = query.offset(offset)

    if limit is not None:
        query = query.limit(limit)

    projects = query.all()

    for project in projects:
        project._num_samples = len(project.samples)

    if not persist_session:
        self.close_session()
    return projects


def get_num_projects(self) -> int:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.query(models.Project).count()
    if not persist_session:
        self.close_session()
    return res


def get_project_by_name(self, name: str) -> models.Project:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    project = self._session.query(models.Project).where(
        models.Project.name == name
    ).first()
    if not persist_session:
        self.close_session()
    return project


def delete_project(
    self, project_id: int,
    commit: bool = True
) -> None:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    project = self._session.get(models.Project, project_id)
    if not project:
        raise exceptions.ElementDoesNotExist(f"Project with id {project_id} does not exist")

    self._session.delete(project)
    if commit:
        self._session.commit()

    if not persist_session:
        self.close_session()


def update_project(
    self, project_id: int,
    name: Optional[str] = None,
    description: Optional[str] = None,
    commit: bool = True
) -> models.Project:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    project = self._session.get(models.Project, project_id)
    if not project:
        raise exceptions.ElementDoesNotExist(f"Project with id {project_id} does not exist")

    if name is not None:
        project.name = name
    if description is not None:
        project.description = description

    if commit:
        self._session.commit()
        self._session.refresh(project)

    if not persist_session:
        self.close_session()
    return project


def project_contains_sample_with_name(
    self, project_id: int, sample_name: str
) -> bool:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    project = self._session.get(models.Project, project_id)
    if not project:
        raise exceptions.ElementDoesNotExist(f"Project with id {project_id} does not exist")

    res = self._session.query(models.Sample).where(
        models.Sample.name == sample_name
    ).where(
        models.Sample.project_id == project_id
    ).first() is not None

    if not persist_session:
        self.close_session()
    return res
