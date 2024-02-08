from uuid import uuid4
from typing import Optional

from ...categories import FileType
from ... import models, logger, tools
from .. import exceptions


def create_file(
    self, name: str, type: FileType, uploader_id: int, extension: str,
    uuid: Optional[str] = None, description: Optional[str] = None, commit: bool = True
) -> models.File:
    
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (_ := self._session.get(models.User, uploader_id)) is None:
        raise exceptions.ElementDoesNotExist(f"User with id '{uploader_id}', not found.")
    
    if uuid is None:
        uuid = str(uuid4())

    name = tools.make_filenameable(name)[:64]

    file = models.File(
        name=name,
        type_id=type.value.id,
        description=description,
        extension=extension,
        uuid=uuid,
        uploader_id=uploader_id
    )

    self._session.add(file)

    if commit:
        self._session.commit()
        self._session.refresh(file)

    if not persist_session:
        self.close_session()

    return file


def get_file(self, file_id: int) -> models.File:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.get(models.File, file_id)

    if not persist_session:
        self.close_session()
    return res


def get_files(self, uploader_id: Optional[int] = None) -> list[models.File]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.File)
    if uploader_id:
        query = query.filter(models.File.uploader_id == uploader_id)

    res = query.all()

    if not persist_session:
        self.close_session()
    return res


def delete_file(self, file_id: int, commit: bool = True) -> None:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (file := self._session.get(models.File, file_id)) is None:
        raise exceptions.ElementDoesNotExist(f"File with id '{file_id}', not found.")
    
    for link in self._session.query(models.SeqRequestFileLink).filter(models.SeqRequestFileLink.file_id == file_id).all():
        self._session.delete(link)

    for link in self._session.query(models.ExperimentFileLink).filter(models.ExperimentFileLink.file_id == file_id).all():
        self._session.delete(link)
        
    self._session.delete(file)

    if commit:
        self._session.commit()

    if not persist_session:
        self.close_session()
    return None