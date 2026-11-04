from uuid6 import uuid7
import sqlalchemy as sa
from sqlalchemy import sql

from ..models import MediaFile, User, links, SeqRequest
from ..categories import MediaFileType, AccessLevel, SeqRequestStatus
from ..core import utils


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
        type=type,
        extension=extension.lower().strip(),
        uuid=uuid or uuid7().__str__(),
        uploader_id=uploader_id,
        size_bytes=size_bytes,
        experiment_id=experiment_id,
        seq_request_id=seq_request_id,
        lab_prep_id=lab_prep_id,
    )

def access_level(user_id: int) -> sql.ColumnElement[AccessLevel]:
    is_admin = sa.select(1).where(User.id == user_id, User.is_admin)
    is_insider = sa.select(1).where(User.id == user_id, User.is_insider)
    # Compare MediaFile's own column: a subquery whose only FROM is MediaFile is not auto-correlated,
    # so it would ask "has the viewer uploaded any file" instead of "this file".
    is_uploader = MediaFile.uploader_id == user_id

    # Files of a seq request follow the request: readable by its requestor and group members.
    # Experiment and lab prep files have no client branch, so only insiders can access them.
    can_read_request = sa.select(1).where(
        SeqRequest.id == MediaFile.seq_request_id,
        sa.or_(
            SeqRequest.requestor_id == user_id,
            sa.select(1).where(
                (links.UserAffiliation.user_id == user_id) &
                (links.UserAffiliation.group_id == SeqRequest.group_id)
            ).correlate_except(links.UserAffiliation).exists(),
        ),
    ).correlate_except(SeqRequest)

    # Removing a file is an edit of the request: the uploader may do it only while the request is a draft.
    request_is_draft = sa.select(1).where(
        SeqRequest.id == MediaFile.seq_request_id,
        SeqRequest.status == SeqRequestStatus.DRAFT,
    ).correlate_except(SeqRequest)

    return sa.case(
        (sa.exists(is_admin), AccessLevel.ADMIN),
        (sa.exists(is_insider), AccessLevel.INSIDER),
        (is_uploader & sa.exists(request_is_draft), AccessLevel.WRITE),
        (is_uploader | sa.exists(can_read_request), AccessLevel.READ),
        else_=AccessLevel.NONE
    )


def search(
    uploader_name: str | None = None,
    statement: sa.Select[MediaFile] = sa.select(MediaFile),
) -> sa.Select[MediaFile]:
    """Fuzzy search on the uploader's full name."""
    if uploader_name is None:
        return statement

    full_name = User.name.expression
    return statement.join(User, MediaFile.uploader_id == User.id).where(
        utils.safe_trgm_search(full_name, uploader_name)
    ).order_by(sa.func.similarity(full_name, uploader_name).desc())


def select(
    id: int | None = None,
    uploader_id: int | None = None,
    experiment_id: int | None = None,
    seq_request_id: int | None = None,
    lab_prep_id: int | None = None,
    type_in: list[MediaFileType] | None = None,
    type: MediaFileType | None = None,
    viewer_id: int | None = None,
    statement: sa.Select[MediaFile] = sa.select(MediaFile),
) -> sa.Select[MediaFile]:
    statement = statement.where(*where_clauses(
        id=id, uploader_id=uploader_id, experiment_id=experiment_id,
        seq_request_id=seq_request_id, lab_prep_id=lab_prep_id,
        viewer_id=viewer_id, type_in=type_in, type=type
    ))
    return statement

def permissions(media_file_id: int, user_id: int) -> sql.Select[AccessLevel]:
    return sa.select(access_level(user_id)).where(MediaFile.id == media_file_id)


def where_clauses(
    id: int | None = None,
    uploader_id: int | None = None,
    experiment_id: int | None = None,
    seq_request_id: int | None = None,
    lab_prep_id: int | None = None,
    type_in: list[MediaFileType] | None = None,
    type: MediaFileType | None = None,
    viewer_id: int | None = None,
) -> list[sa.ColumnElement[bool]]:
    """Return WHERE clauses for filtering media files.
    Reusable in correlated subqueries where .subquery() would break correlation.
    """
    clauses: list[sa.ColumnElement[bool]] = []

    if id is not None:
        clauses.append(MediaFile.id == id)
    if uploader_id:
        clauses.append(MediaFile.uploader_id == uploader_id)
    if experiment_id is not None:
        clauses.append(MediaFile.experiment_id == experiment_id)
    if seq_request_id is not None:
        clauses.append(MediaFile.seq_request_id == seq_request_id)
    if lab_prep_id is not None:
        clauses.append(MediaFile.lab_prep_id == lab_prep_id)
    if type_in is not None:
        clauses.append(MediaFile.type.in_(type_in))
    if type is not None:
        clauses.append(MediaFile.type == type)
    if viewer_id is not None:
        clauses.append(access_level(viewer_id) >= AccessLevel.READ)

    return clauses