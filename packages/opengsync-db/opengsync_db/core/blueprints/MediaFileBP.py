from uuid_extensions import uuid7str
from typing import Optional

from sqlalchemy.sql.base import ExecutableOption

from ...categories import MediaFileType
from ... import models
from ..DBBlueprint import DBBlueprint
from .. import exceptions


class MediaFileBP(DBBlueprint):
    @DBBlueprint.transaction
    def create(
        self, name: str, type: MediaFileType,
        uploader_id: int, extension: str, size_bytes: int,
        uuid: str | None = None,
        seq_request_id: int | None = None,
        experiment_id: int | None = None,
        lab_prep_id: int | None = None,
        flush: bool = True
    ) -> models.MediaFile:
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
        
        if uuid is None:
            uuid = uuid7str()

        name = name[:models.MediaFile.name.type.length]

        file = models.MediaFile(
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

        self.db.session.add(file)

        if flush:
            self.db.flush()
        return file

    @DBBlueprint.transaction
    def get(self, file_id: int, options: ExecutableOption | None = None) -> models.MediaFile | None:
        if options is not None:
            res = self.db.session.query(models.MediaFile).options(options).filter(models.MediaFile.id == file_id).first()
        else:
            res = self.db.session.get(models.MediaFile, file_id)
        return res

    @DBBlueprint.transaction
    def delete(self, file_id: int, flush: bool = True):
        if (file := self.db.session.get(models.MediaFile, file_id)) is None:
            raise exceptions.ElementDoesNotExist(f"File with id '{file_id}', not found.")

        self.db.session.delete(file)
        if flush:
            self.db.flush()

    @DBBlueprint.transaction
    def find(
        self,
        uploader_id: int | None = None,
        experiment_id: int | None = None,
        seq_request_id: int | None = None,
        lab_prep_id: int | None = None,
        limit: int | None = None,
        options: ExecutableOption | None = None,
    ) -> list[models.MediaFile]:
        query = self.db.session.query(models.MediaFile)
        if uploader_id:
            query = query.where(models.MediaFile.uploader_id == uploader_id)
        if experiment_id is not None:
            query = query.where(models.MediaFile.experiment_id == experiment_id)
        if seq_request_id is not None:
            query = query.where(models.MediaFile.seq_request_id == seq_request_id)
        if lab_prep_id is not None:
            query = query.where(models.MediaFile.lab_prep_id == lab_prep_id)

        if options is not None:
            query = query.options(options)

        if limit is not None:
            query = query.limit(limit)
    
        res = query.all()

        return res
    
    @DBBlueprint.transaction
    def update(self, file: models.MediaFile):
        self.db.session.add(file)

    @DBBlueprint.transaction
    def permissions_check(self, user_id: int, file_id: int) -> bool:
        if (file := self.db.session.get(models.MediaFile, file_id)) is None:
            raise exceptions.ElementDoesNotExist(f"File with id '{file_id}', not found.")
        
        # FIXME: proper permission check
        res = file.uploader_id == user_id
        return res
    
    @DBBlueprint.transaction
    def __getitem__(self, file_id: int) -> models.MediaFile:
        if (file := self.db.session.get(models.MediaFile, file_id)) is None:
            raise exceptions.ElementDoesNotExist(f"File with id '{file_id}', not found.")
        return file