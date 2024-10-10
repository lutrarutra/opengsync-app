from typing import Optional, TYPE_CHECKING

from limbless_db import models

if TYPE_CHECKING:
    from ..DBHandler import DBHandler
from .. import exceptions


def create_comment(
    self: "DBHandler", text: str, author_id: int, file_id: Optional[int] = None, commit: bool = True
) -> models.Comment:
    if not (persist_session := self._session is not None):
        self.open_session()

    comment = models.Comment(
        text=text.strip()[:models.Comment.text.type.length],
        author_id=author_id,
        file_id=file_id,
    )
    self.session.add(comment)

    if commit:
        self.session.commit()
        self.session.refresh(comment)

    if not persist_session:
        self.close_session()

    return comment


def get_comment(self: "DBHandler", comment_id: int) -> Optional[models.Comment]:
    if not (persist_session := self._session is not None):
        self.open_session()

    res = self.session.get(models.Comment, comment_id)

    if not persist_session:
        self.close_session()
    return res


def get_comments(self: "DBHandler", author_id: Optional[int] = None, file_id: Optional[int] = None) -> list[models.Comment]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.Comment)

    if author_id is not None:
        query = query.filter(models.Comment.author_id == author_id)
    if file_id is not None:
        query = query.filter(models.Comment.file_id == file_id)

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


def add_experiment_comment(self: "DBHandler", experiment_id: int, comment_id: int, commit: bool = True):
    if not (persist_session := self._session is not None):
        self.open_session()

    if (experiment := self.session.get(models.Experiment, experiment_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Experiment with id '{experiment_id}', not found.")
    
    if (comment := self.session.get(models.Comment, comment_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Comment with id '{comment_id}', not found.")
    
    experiment.comments.append(comment)
    self.session.add(experiment)
    if commit:
        self.session.commit()

    if not persist_session:
        self.close_session()


def add_seq_request_comment(self: "DBHandler", seq_request_id: int, comment_id: int, commit: bool = True):
    if not (persist_session := self._session is not None):
        self.open_session()

    if (seq_request := self.session.get(models.SeqRequest, seq_request_id)) is None:
        raise exceptions.ElementDoesNotExist(f"SeqRequest with id '{seq_request_id}', not found.")
    
    if (comment := self.session.get(models.Comment, comment_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Comment with id '{comment_id}', not found.")
    
    seq_request.comments.append(comment)
    self.session.add(seq_request)
    if commit:
        self.session.commit()

    if not persist_session:
        self.close_session()


def remove_experiment_comment(self: "DBHandler", experiment_id: int, comment_id: int, commit: bool = True):
    if not (persist_session := self._session is not None):
        self.open_session()

    if (experiment := self.session.get(models.Experiment, experiment_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Experiment with id '{experiment_id}', not found.")
    
    if (comment := self.session.get(models.Comment, comment_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Comment with id '{comment_id}', not found.")
    
    experiment.comments.remove(comment)
    self.session.add(experiment)
    if commit:
        self.session.commit()

    if not persist_session:
        self.close_session()


def remove_seq_request_comment(self: "DBHandler", seq_request_id: int, comment_id: int, commit: bool = True):
    if not (persist_session := self._session is not None):
        self.open_session()

    if (seq_request := self.session.get(models.SeqRequest, seq_request_id)) is None:
        raise exceptions.ElementDoesNotExist(f"SeqRequest with id '{seq_request_id}', not found.")
    
    if (comment := self.session.get(models.Comment, comment_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Comment with id '{comment_id}', not found.")
    
    seq_request.comments.remove(comment)
    self.session.add(seq_request)
    if commit:
        self.session.commit()

    if not persist_session:
        self.close_session()
