from uuid import uuid4
from typing import Optional, TYPE_CHECKING

from werkzeug.utils import secure_filename
from sqlalchemy.sql.operators import and_

if TYPE_CHECKING:
    from ..DBHandler import DBHandler
from ...categories import FileTypeEnum
from ... import models
from .. import exceptions


def create_file(
    self: "DBHandler", name: str, type: FileTypeEnum, uploader_id: int, extension: str, size_bytes: int,
    uuid: Optional[str] = None, commit: bool = True
) -> models.File:
    
    if not (persist_session := self._session is not None):
        self.open_session()

    if (_ := self.session.get(models.User, uploader_id)) is None:
        raise exceptions.ElementDoesNotExist(f"User with id '{uploader_id}', not found.")
    
    if uuid is None:
        uuid = str(uuid4())

    name = secure_filename(name).strip()[:models.File.name.type.length]

    file = models.File(
        name=name,
        type_id=type.id,
        extension=extension.lower().strip(),
        uuid=uuid,
        uploader_id=uploader_id,
        size_bytes=size_bytes
    )

    self.session.add(file)

    if commit:
        self.session.commit()
        self.session.refresh(file)

    if not persist_session:
        self.close_session()

    return file


def get_file(self: "DBHandler", file_id: int) -> Optional[models.File]:
    if not (persist_session := self._session is not None):
        self.open_session()

    res = self.session.get(models.File, file_id)

    if not persist_session:
        self.close_session()
    return res


def get_files(self: "DBHandler", uploader_id: Optional[int] = None) -> list[models.File]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.File)
    if uploader_id:
        query = query.where(models.File.uploader_id == uploader_id)

    res = query.all()

    if not persist_session:
        self.close_session()
    return res


def file_permissions_check(self: "DBHandler", user_id: int, file_id: int) -> bool:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (_ := self.session.get(models.User, user_id)) is None:
        raise exceptions.ElementDoesNotExist(f"User with id '{user_id}', not found.")
    
    if (_ := self.session.get(models.File, file_id)) is None:
        raise exceptions.ElementDoesNotExist(f"File with id '{file_id}', not found.")
    
    res = self.session.query(models.File.id).filter(
        models.File.id == file_id
    ).join(
        models.SeqRequest,
        models.SeqRequest.requestor_id == user_id
    ).join(
        models.SeqRequestFileLink,
        and_(
            models.SeqRequestFileLink.seq_request_id == models.SeqRequest.id,
            models.SeqRequestFileLink.file_id == file_id
        )
    ).distinct().all()

    if not persist_session:
        self.close_session()

    return file_id in [r[0] for r in res]