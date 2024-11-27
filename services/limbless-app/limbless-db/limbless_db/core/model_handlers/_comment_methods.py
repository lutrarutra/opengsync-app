from typing import Optional, TYPE_CHECKING

from limbless_db import models

if TYPE_CHECKING:
    from ..DBHandler import DBHandler
from .. import exceptions


def create_comment(
    self: "DBHandler", text: str, author_id: int, file_id: Optional[int] = None,
    seq_request_id: Optional[int] = None,
    experiment_id: Optional[int] = None,
    lab_prep_id: Optional[int] = None
) -> models.Comment:
    if not (persist_session := self._session is not None):
        self.open_session()

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
        
    if file_id is not None:
        if self.session.get(models.File, file_id) is None:
            raise exceptions.ElementDoesNotExist(f"File with id '{file_id}', not found.")
        
    if self.session.get(models.User, author_id) is None:
        raise exceptions.ElementDoesNotExist(f"User with id '{author_id}', not found.")

    comment = models.Comment(
        text=text.strip()[:models.Comment.text.type.length],
        author_id=author_id,
        file_id=file_id,
        experiment_id=experiment_id,
        seq_request_id=seq_request_id,
        lab_prep_id=lab_prep_id
    )
    self.session.add(comment)
    self.session.commit()
    self.session.refresh(comment)

    if not persist_session:
        self.close_session()

    return comment


def get_comment(self: "DBHandler", comment_id: int) -> models.Comment | None:
    if not (persist_session := self._session is not None):
        self.open_session()

    res = self.session.get(models.Comment, comment_id)

    if not persist_session:
        self.close_session()
    return res


def get_comments(
    self: "DBHandler",
    author_id: Optional[int] = None,
    file_id: Optional[int] = None,
    experiment_id: Optional[int] = None,
    seq_request_id: Optional[int] = None,
    lab_prep_id: Optional[int] = None
) -> list[models.Comment]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.Comment)

    if author_id is not None:
        query = query.where(models.Comment.author_id == author_id)
    if file_id is not None:
        query = query.where(models.Comment.file_id == file_id)
    if experiment_id is not None:
        query = query.where(models.Comment.experiment_id == experiment_id)
    if seq_request_id is not None:
        query = query.where(models.Comment.seq_request_id == seq_request_id)
    if lab_prep_id is not None:
        query = query.where(models.Comment.lab_prep_id == lab_prep_id)

    res = query.all()

    if not persist_session:
        self.close_session()
    return res


def delete_comment(self: "DBHandler", comment_id: int) -> None:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (comment := self.session.get(models.Comment, comment_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Comment with id {comment_id} does not exist")

    self.session.delete(comment)
    self.session.commit()

    if not persist_session:
        self.close_session()