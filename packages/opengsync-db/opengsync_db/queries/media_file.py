import sqlalchemy as sa

from ..models import MediaFile
from ..categories import MediaFileType


def create(
    name: str,
    type: MediaFileType,
    uploader_id: int, extension: str, size_bytes: int,
    uuid: str | None = None,
    seq_request_id: int | None = None,
    experiment_id: int | None = None,
    lab_prep_id: int | None = None,
) -> MediaFile:
    name = name[:MediaFile.name.type.length]

    return MediaFile(
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


def select(
    id: int | None = None,
    uploader_id: int | None = None,
    experiment_id: int | None = None,
    seq_request_id: int | None = None,
    lab_prep_id: int | None = None,
    statement: sa.Select[tuple[MediaFile]] = sa.select(MediaFile),
) -> sa.Select[tuple[MediaFile]]:
    if id is not None:
        statement = statement.where(MediaFile.id == id)
    if uploader_id:
        statement = statement.where(MediaFile.uploader_id == uploader_id)
    if experiment_id is not None:
        statement = statement.where(MediaFile.experiment_id == experiment_id)
    if seq_request_id is not None:
        statement = statement.where(MediaFile.seq_request_id == seq_request_id)
    if lab_prep_id is not None:
        statement = statement.where(MediaFile.lab_prep_id == lab_prep_id)
    
    return statement