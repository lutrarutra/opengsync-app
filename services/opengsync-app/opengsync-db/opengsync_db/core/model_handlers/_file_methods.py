from uuid import uuid4
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..DBHandler import DBHandler
from ...categories import FileTypeEnum
from ... import models
from .. import exceptions


def create_file(
    self: "DBHandler", name: str, type: FileTypeEnum,
    uploader_id: int, extension: str, size_bytes: int,
    uuid: Optional[str] = None,
    seq_request_id: Optional[int] = None,
    experiment_id: Optional[int] = None,
    lab_prep_id: Optional[int] = None,
    flush: bool = True
) -> models.File:
    
    if not (persist_session := self._session is not None):
        self.open_session()

    if (_ := self.session.get(models.User, uploader_id)) is None:
        raise exceptions.ElementDoesNotExist(f"User with id '{uploader_id}', not found.")
    
    if seq_request_id is not None:
        if experiment_id is not None:
            raise Exception("Cannot have both seq_request_id and experiment_id.")
        if lab_prep_id is not None:
            raise Exception("Cannot have both seq_request_id and lab_prep_id.")
        if self.session.get(models.SeqRequest, seq_request_id) is None:
            raise exceptions.ElementDoesNotExist(f"SeqRequest with id '{seq_request_id}', not found.")
        
    elif experiment_id is not None:
        if lab_prep_id is not None:
            raise Exception("Cannot have both experiment_id and lab_prep_id.")
        if self.session.get(models.Experiment, experiment_id) is None:
            raise exceptions.ElementDoesNotExist(f"Experiment with id '{experiment_id}', not found.")
        
    elif lab_prep_id is not None:
        if self.session.get(models.LabPrep, lab_prep_id) is None:
            raise exceptions.ElementDoesNotExist(f"LabPrep with id '{lab_prep_id}', not found.")
    
    if uuid is None:
        uuid = str(uuid4())

    name = name[:models.File.name.type.length]

    file = models.File(
        name=name,
        type_id=type.id,
        extension=extension.lower().strip(),
        uuid=uuid,
        uploader_id=uploader_id,
        size_bytes=size_bytes,
        experiment_id=experiment_id,
        seq_request_id=seq_request_id,
        lab_prep_id=lab_prep_id,
    )

    self.session.add(file)

    if flush:
        self.session.flush()

    if not persist_session:
        self.close_session()

    return file


def get_file(self: "DBHandler", file_id: int) -> models.File | None:
    if not (persist_session := self._session is not None):
        self.open_session()

    res = self.session.get(models.File, file_id)

    if not persist_session:
        self.close_session()
    return res


def delete_file(self: "DBHandler", file_id: int, flush: bool = True):
    if not (persist_session := self._session is not None):
        self.open_session()

    if (file := self.session.get(models.File, file_id)) is None:
        raise exceptions.ElementDoesNotExist(f"File with id '{file_id}', not found.")

    self.session.delete(file)
    if flush:
        self.session.flush()

    if not persist_session:
        self.close_session()


def get_files(
    self: "DBHandler",
    uploader_id: Optional[int] = None,
    experiment_id: Optional[int] = None,
    seq_request_id: Optional[int] = None,
    lab_prep_id: Optional[int] = None
) -> list[models.File]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.File)
    if uploader_id:
        query = query.where(models.File.uploader_id == uploader_id)
    if experiment_id is not None:
        query = query.where(models.File.experiment_id == experiment_id)
    if seq_request_id is not None:
        query = query.where(models.File.seq_request_id == seq_request_id)
    if lab_prep_id is not None:
        query = query.where(models.File.lab_prep_id == lab_prep_id)

    res = query.all()

    if not persist_session:
        self.close_session()
    return res


def file_permissions_check(self: "DBHandler", user_id: int, file_id: int) -> bool:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (_ := self.session.get(models.User, user_id)) is None:
        raise exceptions.ElementDoesNotExist(f"User with id '{user_id}', not found.")
    
    if (file := self.session.get(models.File, file_id)) is None:
        raise exceptions.ElementDoesNotExist(f"File with id '{file_id}', not found.")
    
    # FIXME: proper permission check
    res = file.uploader_id == user_id

    if not persist_session:
        self.close_session()

    return res