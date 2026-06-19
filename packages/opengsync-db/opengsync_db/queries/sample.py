import sqlalchemy as sa

from ..models import Library, Sample, links, User, SeqRequest
from ..categories import (
    LibraryStatus, UserRole, AccessLevel, SeqRequestStatus, SampleStatus
)
from ..core import utils


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
        links.SampleLibraryLink.sample_id == Sample.id,
        Library.id == links.SampleLibraryLink.library_id,
        Library.seq_request_id == SeqRequest.id,
        SeqRequest.status_id == SeqRequestStatus.DRAFT.id,
        sa.or_(
            SeqRequest.requestor_id == user_id,
            sa.select(1).where(
                (links.UserAffiliation.user_id == user_id) &
                (links.UserAffiliation.group_id == SeqRequest.group_id)
            ).correlate_except(links.UserAffiliation).exists()
        ),
        ~sa.select(1).where(
            (links.SampleLibraryLink.sample_id == Sample.id) &
            (Library.id == links.SampleLibraryLink.library_id) &
            (Library.seq_request_id == SeqRequest.id) &
            (Library.status_id != LibraryStatus.DRAFT.id)
        ).correlate_except(links.SampleLibraryLink, Library).exists()
    ).correlate_except(links.SampleLibraryLink, Library, SeqRequest)

    has_read_access = sa.select(1).where(
        links.SampleLibraryLink.sample_id == Sample.id,
        Library.id == links.SampleLibraryLink.library_id,
        Library.seq_request_id == SeqRequest.id,
        sa.or_(
            SeqRequest.requestor_id == user_id,
            sa.select(1).where(
                (links.UserAffiliation.user_id == user_id) &
                (links.UserAffiliation.group_id == SeqRequest.group_id)
            ).correlate_except(links.UserAffiliation).exists()
        )
    ).correlate_except(links.SampleLibraryLink, Library, SeqRequest)

    return sa.case(
        (sa.exists(is_admin), AccessLevel.ADMIN),
        (sa.exists(is_insider), AccessLevel.INSIDER),
        (sa.exists(has_write_access), AccessLevel.WRITE),
        (sa.exists(has_read_access), AccessLevel.READ),
        else_=AccessLevel.NONE
    )



def search(
    name: str | None = None,
    owner_name: str | None = None,
    name_weight: float = 0.5,
    owner_name_weight: float = 0.5,
    statement: sa.Select[tuple[Sample]] = sa.select(Sample),
) -> sa.Select[tuple[Sample]]:
    filter_conditions: list[sa.ColumnElement[bool]] = []
    relevance = sa.literal(0.0)

    if name is not None:
        filter_conditions.append(utils.safe_trgm_search(Sample.name, name))
        relevance += sa.func.similarity(Sample.name, name) * name_weight

    if owner_name is not None:
        full_name = sa.func.concat(User.first_name, ' ', User.last_name)
        filter_conditions.append(utils.safe_trgm_search(full_name, owner_name))
        relevance += sa.func.similarity(full_name, owner_name) * owner_name_weight

    if not filter_conditions:
        return statement

    statement = statement.where(sa.or_(*filter_conditions))

    if owner_name is not None:
        statement = statement.join(User, Sample.owner_id == User.id)

    return statement.order_by(sa.nulls_last(relevance.desc()))


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
    viewer_id: int | None = None,
    statement: sa.Select[tuple[Sample]] = sa.select(Sample),
) -> sa.Select[tuple[Sample]]:
    return statement.where(*where_clauses(
        id=id,
        user_id=user_id,
        project_id=project_id,
        library_id=library_id,
        pool_id=pool_id,
        seq_request_id=seq_request_id,
        lab_prep_id=lab_prep_id,
        status=status,
        status_in=status_in,
        viewer_id=viewer_id,
    ))


def permissions(sample_id: int, user_id: int) -> sa.Select[tuple[AccessLevel]]:
    return sa.select(access_level(user_id)).where(Sample.id == sample_id)


def where_clauses(
    id: int | None = None,
    user_id: int | None = None,
    project_id: int | None = None,
    library_id: int | None = None,
    pool_id: int | None = None,
    viewer_id: int | None = None,
    seq_request_id: int | None = None,
    lab_prep_id: int | None = None,
    status: SampleStatus | None = None,
    status_in: list[SampleStatus] | None = None,
) -> list[sa.ColumnElement[bool]]:
    """Return WHERE clauses for filtering samples. 
    Reusable in correlated subqueries where .subquery() would break correlation.
    """
    clauses: list[sa.ColumnElement[bool]] = []

    if id is not None:
        clauses.append(Sample.id == id)

    if user_id is not None:
        clauses.append(Sample.owner_id == user_id)

    if project_id is not None:
        clauses.append(Sample.project_id == project_id)

    if library_id is not None:
        clauses.append(
            sa.select(1).where(
                (links.SampleLibraryLink.sample_id == Sample.id) &
                (links.SampleLibraryLink.library_id == library_id)
            ).correlate_except(links.SampleLibraryLink).exists()
        )

    if pool_id is not None:
        clauses.append(
            sa.select(1).where(
                (links.SampleLibraryLink.sample_id == Sample.id) &
                (Library.id == links.SampleLibraryLink.library_id) &
                (Library.pool_id == pool_id)
            ).correlate_except(links.SampleLibraryLink, Library).exists()
        )

    if lab_prep_id is not None:
        clauses.append(
            sa.select(1).where(
                (links.SampleLibraryLink.sample_id == Sample.id) &
                (Library.id == links.SampleLibraryLink.library_id) &
                (Library.lab_prep_id == lab_prep_id)
            ).correlate_except(links.SampleLibraryLink, Library).exists()
        )

    if seq_request_id is not None:
        clauses.append(
            sa.select(1).where(
                (links.SampleLibraryLink.sample_id == Sample.id) &
                (Library.id == links.SampleLibraryLink.library_id) &
                (Library.seq_request_id == seq_request_id)
            ).correlate_except(links.SampleLibraryLink, Library).exists()
        )

    if status is not None:
        clauses.append(Sample.status_id == status.id)

    if status_in is not None:
        clauses.append(Sample.status_id.in_([s.id for s in status_in]))

    if viewer_id is not None:
        clauses.append(access_level(viewer_id) >= AccessLevel.READ)

    return clauses