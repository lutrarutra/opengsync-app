from typing import Optional

from limbless_db import models

from .. import exceptions


def create_comment(
    self, text: str, author_id: int, file_id: Optional[int] = None, commit: bool = True
) -> models.Comment:
    if not (persist_session := self._session is not None):
        self.open_session()

    comment = models.Comment(
        text=text.strip()[:models.Comment.text.type.length],
        author_id=author_id,
        file_id=file_id,
    )
    self._session.add(comment)

    if commit:
        self._session.commit()
        self._session.refresh(comment)

    if not persist_session:
        self.close_session()

    return comment


def get_comment(self, comment_id: int) -> Optional[models.Comment]:
    if not (persist_session := self._session is not None):
        self.open_session()

    res = self._session.get(models.Comment, comment_id)

    if not persist_session:
        self.close_session()
    return res


def get_comments(self, author_id: Optional[int] = None, file_id: Optional[int] = None) -> list[models.Comment]:
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self._session.query(models.Comment)

    if author_id is not None:
        query = query.filter(models.Comment.author_id == author_id)
    if file_id is not None:
        query = query.filter(models.Comment.file_id == file_id)

    res = query.all()

    if not persist_session:
        self.close_session()
    return res


def delete_comment(self, comment_id: int) -> None:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (comment := self._session.get(models.Comment, comment_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Comment with id {comment_id} does not exist")

    self._session.delete(comment)
    self._session.commit()

    if not persist_session:
        self.close_session()


def add_experiment_comment(self, experiment_id: int, comment_id: int, commit: bool = True):
    if not (persist_session := self._session is not None):
        self.open_session()

    if (experiment := self._session.get(models.Experiment, experiment_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Experiment with id '{experiment_id}', not found.")
    
    if (comment := self._session.get(models.Comment, comment_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Comment with id '{comment_id}', not found.")
    
    experiment = self._session.get(models.Experiment, experiment_id)
    experiment.comments.append(comment)
    self._session.add(experiment)
    if commit:
        self._session.commit()

    if not persist_session:
        self.close_session()


def add_seq_request_comment(self, seq_request_id: int, comment_id: int, commit: bool = True):
    if not (persist_session := self._session is not None):
        self.open_session()

    if (seq_request := self._session.get(models.SeqRequest, seq_request_id)) is None:
        raise exceptions.ElementDoesNotExist(f"SeqRequest with id '{seq_request_id}', not found.")
    
    if (comment := self._session.get(models.Comment, comment_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Comment with id '{comment_id}', not found.")
    
    seq_request = self._session.get(models.SeqRequest, seq_request_id)
    seq_request.comments.append(comment)
    self._session.add(seq_request)
    if commit:
        self._session.commit()

    if not persist_session:
        self.close_session()


def remove_experiment_comment(self, experiment_id: int, comment_id: int, commit: bool = True):
    if not (persist_session := self._session is not None):
        self.open_session()

    if (experiment := self._session.get(models.Experiment, experiment_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Experiment with id '{experiment_id}', not found.")
    
    if (comment := self._session.get(models.Comment, comment_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Comment with id '{comment_id}', not found.")
    
    experiment = self._session.get(models.Experiment, experiment_id)
    experiment.comments.remove(comment)
    self._session.add(experiment)
    if commit:
        self._session.commit()

    if not persist_session:
        self.close_session()


def remove_seq_request_comment(self, seq_request_id: int, comment_id: int, commit: bool = True):
    if not (persist_session := self._session is not None):
        self.open_session()

    if (seq_request := self._session.get(models.SeqRequest, seq_request_id)) is None:
        raise exceptions.ElementDoesNotExist(f"SeqRequest with id '{seq_request_id}', not found.")
    
    if (comment := self._session.get(models.Comment, comment_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Comment with id '{comment_id}', not found.")
    
    seq_request = self._session.get(models.SeqRequest, seq_request_id)
    seq_request.comments.remove(comment)
    self._session.add(seq_request)
    if commit:
        self._session.commit()

    if not persist_session:
        self.close_session()
