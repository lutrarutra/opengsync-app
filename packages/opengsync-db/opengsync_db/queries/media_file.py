import sqlalchemy as sa
from sqlalchemy import sql

from ..models import MediaFile, User, links, SeqRequest
from ..categories import MediaFileType, AccessLevel, UserRole


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

def access_level(user_id: int) -> sql.ColumnElement[AccessLevel]:
    is_admin = sa.select(1).where(
        User.id == user_id,
        User.role_id == UserRole.ADMIN.id
    )

    is_insider = sa.select(1).where(
        User.id == user_id,
        User.role_id.isin([UserRole.BIOINFORMATICIAN.id, UserRole.TECHNICIAN.id])
    )

    is_owner = sa.select(1).where(
        MediaFile.uploader_id == user_id
    )

    has_read_access = sa.select(1).where(
        sa.exists().where(
            (MediaFile.seq_request_id == SeqRequest.id) &
            (links.UserAffiliation.user_id == user_id) &
            (links.UserAffiliation.group_id == SeqRequest.group_id)
        )
    )

    return sa.case(
        (sa.exists(is_admin), AccessLevel.ADMIN),
        (sa.exists(is_insider), AccessLevel.INSIDER),
        (sa.exists(is_owner), AccessLevel.WRITE),
        (sa.exists(has_read_access), AccessLevel.READ),
        else_=AccessLevel.NONE
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

def permissions(media_file_id: int, user_id: int) -> sql.Select[tuple[AccessLevel]]:
    return sa.select(access_level(user_id)).where(MediaFile.id == media_file_id)