from typing import Optional

from sqlalchemy.orm import selectinload
from sqlmodel import and_

from ... import models, logger
from .. import exceptions
from ...categories import AccessType, UserRole


def get_user_project_access(
    self, user_id: int, project_id: int
) -> Optional[list[AccessType]]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (user := self._session.get(models.User, user_id)) is None:
        raise exceptions.ElementDoesNotExist(f"User with id {user_id} does not exist")
    
    if (project := self._session.get(models.Project, project_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Project with id {project_id} does not exist")

    if user.role_type == UserRole.ADMIN:
        access = [AccessType.READ, AccessType.READWRITE]
    elif user.role_type == UserRole.BIOINFORMATICIAN:
        access = [AccessType.READ, AccessType.READWRITE]
    elif user.role_type == UserRole.TECHNICIAN:
        access = [AccessType.READ]
    elif user.role_type == UserRole.CLIENT:
        if self._session.get(models.Project, project_id) is None:
            raise exceptions.ElementDoesNotExist(f"Project with id {project_id} does not exist")

        if user.id == project.owner_id:
            access = [AccessType.READ, AccessType.READWRITE]
        else:
            res: models.ProjectUserLink = self._session.query(models.ProjectUserLink).where(
                models.ProjectUserLink.project_id == project_id,
                models.ProjectUserLink.user_id == user_id
            ).first()

            if res is None:
                access = None
            else:
                access = res.access_type
    else:
        raise exceptions.InvalidRole(f"User with id {user_id} has invalid role {user.role_type}")

    if not persist_session:
        self.close_session()

    return access


def get_user_experiment_access(
    self, user_id: int, experiment_id: int
) -> Optional[list[AccessType]]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (user := self._session.get(models.User, user_id)) is None:
        raise exceptions.ElementDoesNotExist(f"User with id {user_id} does not exist")

    if not persist_session:
        self.close_session()

    if user.role_type == UserRole.ADMIN:
        access = [AccessType.READ, AccessType.READWRITE]
    elif user.role_type == UserRole.BIOINFORMATICIAN:
        access = [AccessType.READ, AccessType.READWRITE]
    elif user.role_type == UserRole.TECHNICIAN:
        access = [AccessType.READ]
    elif user.role_type == UserRole.CLIENT:
        access = None

    return access


def get_user_library_access(
    self, user_id: int, library_id: int
) -> Optional[list[AccessType]]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (user := self._session.get(models.User, user_id)) is None:
        raise exceptions.ElementDoesNotExist(f"User with id {user_id} does not exist")
    
    if (library := self._session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")

    logger.debug(user.role_type)
    if user.role_type == UserRole.ADMIN:
        access = [AccessType.READ, AccessType.READWRITE]
    elif user.role_type == UserRole.BIOINFORMATICIAN:
        access = [AccessType.READ, AccessType.READWRITE]
    elif user.role_type == UserRole.TECHNICIAN:
        access = [AccessType.READ]
    elif user.role_type == UserRole.CLIENT:
        if library.owner_id == user_id:
            access = [AccessType.READ, AccessType.READWRITE]
        else:
            res: models.LibraryUserLink = self._session.query(models.LibraryUserLink).where(
                models.LibraryUserLink.library_id == library_id,
                models.LibraryUserLink.user_id == user_id
            ).first()

            if res is None:
                access = None
            else:
                access = res.access_type
    else:
        raise exceptions.InvalidRole(f"User with id {user_id} has invalid role {user.role_type}")

    if not persist_session:
        self.close_session()

    return access


def get_user_sample_access(
    self, user_id: int, sample_id: int
) -> Optional[list[AccessType]]:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (user := self._session.get(models.User, user_id)) is None:
        raise exceptions.ElementDoesNotExist(f"User with id {user_id} does not exist")

    if user.role_type == UserRole.ADMIN:
        access = [AccessType.READ, AccessType.READWRITE]
    elif user.role_type == UserRole.BIOINFORMATICIAN:
        access = [AccessType.READ, AccessType.READWRITE]
    elif user.role_type == UserRole.TECHNICIAN:
        access = [AccessType.READ]
    elif user.role_type == UserRole.CLIENT:
        if (sample := self._session.get(models.Sample, sample_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Sample with id {sample_id} does not exist")

        access = self.get_user_project_access(user_id, sample.project_id)

    if not persist_session:
        self.close_session()

    return access
