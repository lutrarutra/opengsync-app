from opengsync_db import models

from .. import exceptions
from ..DBBlueprint import DBBlueprint


class CommentBP(DBBlueprint):
    @DBBlueprint.transaction
    def create(
        self, text: str, author_id: int, file_id: int | None = None,
        seq_request_id: int | None = None,
        experiment_id: int | None = None,
        lab_prep_id: int | None = None,
        flush: bool = True
    ) -> models.Comment:
        if seq_request_id is not None:
            if experiment_id is not None:
                raise Exception("Cannot have both seq_request_id and experiment_id.")
            if lab_prep_id is not None:
                raise Exception("Cannot have both seq_request_id and lab_prep_id.")
            if self.db.session.get(models.SeqRequest, seq_request_id) is None:
                raise exceptions.ElementDoesNotExist(f"SeqRequest with id '{seq_request_id}', not found.")
            
        elif experiment_id is not None:
            if lab_prep_id is not None:
                raise Exception("Cannot have both experiment_id and lab_prep_id.")
            if self.db.session.get(models.Experiment, experiment_id) is None:
                raise exceptions.ElementDoesNotExist(f"Experiment with id '{experiment_id}', not found.")
            
        elif lab_prep_id is not None:
            if self.db.session.get(models.LabPrep, lab_prep_id) is None:
                raise exceptions.ElementDoesNotExist(f"LabPrep with id '{lab_prep_id}', not found.")
            
        if file_id is not None:
            if self.db.session.get(models.MediaFile, file_id) is None:
                raise exceptions.ElementDoesNotExist(f"File with id '{file_id}', not found.")
            
        if self.db.session.get(models.User, author_id) is None:
            raise exceptions.ElementDoesNotExist(f"User with id '{author_id}', not found.")

        comment = models.Comment(
            text=text.strip()[:models.Comment.text.type.length],
            author_id=author_id,
            file_id=file_id,
            experiment_id=experiment_id,
            seq_request_id=seq_request_id,
            lab_prep_id=lab_prep_id
        )
        self.db.session.add(comment)

        if flush:
            self.db.flush()
        return comment

    @DBBlueprint.transaction
    def get(self, comment_id: int) -> models.Comment | None:
        res = self.db.session.get(models.Comment, comment_id)
        return res

    @DBBlueprint.transaction
    def find(
        self,
        author_id: int | None = None,
        file_id: int | None = None,
        experiment_id: int | None = None,
        seq_request_id: int | None = None,
        lab_prep_id: int | None = None
    ) -> list[models.Comment]:
        query = self.db.session.query(models.Comment)

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
        return res

    @DBBlueprint.transaction
    def delete(self, comment_id: int, flush: bool = True) -> None:
        if (comment := self.db.session.get(models.Comment, comment_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Comment with id {comment_id} does not exist")

        self.db.session.delete(comment)

        if flush:
            self.db.flush()