import sqlalchemy as sa

from ..models import Library, Sample, links, User, SeqRequest
from ..categories import (
    LibraryStatus, UserRole, AccessLevel, SeqRequestStatus, SampleStatus
)

def create(
    name: str,
    owner_id: int,
    project_id: int,
    status: SampleStatus | None,
) -> Sample:
    return Sample(
        name=name.strip(),
        project_id=project_id,
        owner_id=owner_id,
        status_id=status.id if status is not None else None,
    )


def access_level(user_id: int) -> sa.ColumnElement[AccessLevel]:
    is_admin = sa.select(1).where(
        User.id == user_id,
        User.role_id == UserRole.ADMIN.id
    )

    is_insider = sa.select(1).where(
        User.id == user_id,
        User.role_id.in_([UserRole.BIOINFORMATICIAN.id, UserRole.TECHNICIAN.id])
    )

    has_write_access = sa.select(1).where(
        sa.and_(
            SeqRequest.status_id == SeqRequestStatus.DRAFT.id,
            sa.or_(
                SeqRequest.requestor_id == user_id,
                sa.exists().where(
                    (links.UserAffiliation.user_id == user_id) &
                    (links.UserAffiliation.group_id == SeqRequest.group_id) &
                    (Library.seq_request_id == SeqRequest.id) &
                    (links.SampleLibraryLink.library_id == Library.id) &
                    (links.SampleLibraryLink.sample_id == Sample.id)
                )
            ),
            ~sa.exists().where(
                (links.SampleLibraryLink.sample_id == Sample.id) &
                (Library.id == links.SampleLibraryLink.library_id) &
                (Library.seq_request_id == SeqRequest.id) &
                (Library.status_id != LibraryStatus.DRAFT.id)
            )
        ),
    )

    has_read_access = sa.select(1).where(
        sa.or_(
            SeqRequest.requestor_id == user_id,
            sa.exists().where(
                (links.UserAffiliation.user_id == user_id) &
                (links.UserAffiliation.group_id == SeqRequest.group_id) &
                (Library.seq_request_id == SeqRequest.id) &
                (links.SampleLibraryLink.library_id == Library.id) &
                (links.SampleLibraryLink.sample_id == Sample.id)
            )
        )
    )

    return sa.case(
        (sa.exists(is_admin), AccessLevel.ADMIN),
        (sa.exists(is_insider), AccessLevel.INSIDER),
        (sa.exists(has_write_access), AccessLevel.WRITE),
        (sa.exists(has_read_access), AccessLevel.READ),
        else_=AccessLevel.NONE
    )



def select(
    id: int | None = None,
    user_id: int | None = None,
    project_id: int | None = None,
    library_id: int | None = None,
    pool_id: int | None = None,
    seq_request_id: int | None = None,
    lab_prep_id: int | None = None,
    status: SampleStatus | None = None,
    status_in: list[SampleStatus] | None = None,
    search_name: str | None = None,
    search_owner_name: str | None = None,
    statement: sa.Select[tuple[Sample]] = sa.select(Sample),
) -> sa.Select[tuple[Sample]]:
    if id is not None:
        statement = statement.where(Sample.id == id)

    if user_id is not None:
        statement = statement.where(Sample.owner_id == user_id)

    if project_id is not None:
        statement = statement.where(Sample.project_id == project_id)

    if library_id is not None:
        statement = statement.where(
            sa.exists().where(
                (links.SampleLibraryLink.sample_id == Sample.id) &
                (links.SampleLibraryLink.library_id == library_id)
            )
        )

    if pool_id is not None:
        statement = statement.where(
            sa.exists().where(
                (links.SampleLibraryLink.sample_id == Sample.id) &
                (Library.id == links.SampleLibraryLink.library_id) &
                (Library.pool_id == pool_id)
            )
        )

    if lab_prep_id is not None:
        statement = statement.where(
            sa.exists().where(
                (links.SampleLibraryLink.sample_id == Sample.id) &
                (Library.id == links.SampleLibraryLink.library_id) &
                (Library.lab_prep_id == lab_prep_id)
            )
        )

    if seq_request_id is not None:
        statement = statement.where(
            sa.exists().where(
                (links.SampleLibraryLink.sample_id == Sample.id) &
                (Library.id == links.SampleLibraryLink.library_id) &
                (Library.seq_request_id == seq_request_id)
            )
        )

    if status is not None:
        statement = statement.where(Sample.status_id == status.id)

    if status_in is not None:
        statement = statement.where(Sample.status_id.in_([s.id for s in status_in]))

    if search_name is not None:
        statement = statement.order_by(sa.func.similarity(Sample.name, search_name).desc())
    elif search_owner_name is not None:
        from ..models import User
        statement = statement.join(
            Sample.owner
        ).order_by(sa.func.similarity(User.name, search_owner_name).desc())

    return statement


def permissions(sample_id: int, user_id: int) -> sa.Select[tuple[AccessLevel]]:
    return sa.select(access_level(user_id)).where(Sample.id == sample_id)