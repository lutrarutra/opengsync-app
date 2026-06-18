import sqlalchemy as sa
from sqlalchemy import sql

from ..models import Pool, Contact, Library, User, SeqRequest, links
from ..categories import PoolStatus, PoolType, LibraryType, AccessLevel, UserRole, SeqRequestStatus


def create(
    name: str,
    owner_id: int,
    contact_name: str,
    contact_email: str,
    pool_type: PoolType,
    clone_number: int,
    experiment_id: int | None = None,
    original_pool_id: int | None = None,
    seq_request_id: int | None = None,
    lab_prep_id: int | None = None,
    num_m_reads_requested: float | None = None,
    status: PoolStatus = PoolStatus.DRAFT,
    contact_phone: str | None = None,
) -> Pool:
    return Pool(
        name=name.strip(),
        owner_id=owner_id,
        type_id=pool_type.id,
        seq_request_id=seq_request_id,
        num_m_reads_requested=num_m_reads_requested,
        contact=Contact(
            name=contact_name.strip(),
            email=contact_email.strip(),
            phone=contact_phone.strip() if contact_phone else None
        ),
        lab_prep_id=lab_prep_id,
        status_id=status.id,
        timestamp_stored_utc=sa.func.now() if status == PoolStatus.STORED else None,
        clone_number=clone_number,
        original_pool_id=original_pool_id,
        experiment_id=experiment_id
    )


def access_level(user_id: int) -> sql.ColumnElement[AccessLevel]:
    is_admin = sa.select(1).where(
        User.id == user_id,
        User.role_id == UserRole.ADMIN.id
    )

    is_insider = sa.select(1).where(
        User.id == user_id,
        User.role_id.in_([UserRole.BIOINFORMATICIAN.id, UserRole.TECHNICIAN.id])
    )

    # TODO: This is not entirely correct, as it doesn't account for users having access to the pool through their projects
    # has_write_access = sa.select(1).where(
    #     U
    # )

    has_write_access = sa.and_(
        sa.select(1).where(
            Pool.seq_request_id == SeqRequest.id,
            SeqRequest.status_id == SeqRequestStatus.DRAFT.id,
            sa.or_(
                SeqRequest.requestor_id == user_id,
                sa.select(1).where(
                    (links.UserAffiliation.user_id == user_id),
                    (links.UserAffiliation.group_id == SeqRequest.group_id)
                ).correlate_except(links.UserAffiliation).exists()
            )
        ).correlate_except(SeqRequest).exists()
    )

    has_read_access = sa.and_(
        sa.select(1).where(
            Pool.seq_request_id == SeqRequest.id,
            sa.or_(
                SeqRequest.requestor_id == user_id,
                sa.select(1).where(
                    (links.UserAffiliation.user_id == user_id),
                    (links.UserAffiliation.group_id == SeqRequest.group_id)
                ).correlate_except(links.UserAffiliation).exists()
            )
        ).correlate_except(SeqRequest).exists()
    )

    return sa.case(
        (sa.exists(is_admin), AccessLevel.ADMIN),
        (sa.exists(is_insider), AccessLevel.INSIDER),
        (has_write_access, AccessLevel.WRITE),
        (has_read_access, AccessLevel.READ),
        else_=AccessLevel.NONE
    )


def select(
    id: int | None = None,
    user_id: int | None = None,
    library_id: int | None = None,
    experiment_id: int | None = None,
    lab_prep_id: int | None = None,
    seq_request_id: int | None = None,
    associated_to_experiment: bool | None = None,
    status: PoolStatus | None = None,
    status_in: list[PoolStatus] | None = None,
    library_types_in: list[LibraryType] | None = None,
    type_in: list[PoolType] | None = None,
    viewer_id: int | None = None,
    search_name: str | None = None,
    search_owner_name: str | None = None,
    statement: sa.Select[tuple[Pool]] = sa.select(Pool),
) -> sa.Select[tuple[Pool]]:
    statement = statement.where(*where_clauses(
        id=id,
        user_id=user_id,
        library_id=library_id,
        experiment_id=experiment_id,
        lab_prep_id=lab_prep_id,
        seq_request_id=seq_request_id,
        associated_to_experiment=associated_to_experiment,
        status=status,
        status_in=status_in,
        library_types_in=library_types_in,
        type_in=type_in,
        viewer_id=viewer_id
    ))

    if search_name is not None:
        statement = statement.order_by(sa.func.similarity(Pool.name, search_name).desc())
    if search_owner_name is not None:
        statement = statement.join(
            User,
            User.id == Pool.owner_id
        ).where(
            sa.func.similarity(User.name, search_owner_name) > 0
        ).order_by(
            sa.func.similarity(User.name, search_owner_name).desc()
        )
    return statement


def permissions(pool_id: int, user_id: int) -> sa.Select[tuple[AccessLevel]]:
    return sa.select(access_level(user_id)).where(Pool.id == pool_id)


def where_clauses(
    id: int | None = None,
    user_id: int | None = None,
    library_id: int | None = None,
    experiment_id: int | None = None,
    lab_prep_id: int | None = None,
    seq_request_id: int | None = None,
    associated_to_experiment: bool | None = None,
    status: PoolStatus | None = None,
    status_in: list[PoolStatus] | None = None,
    library_types_in: list[LibraryType] | None = None,
    type_in: list[PoolType] | None = None,
    viewer_id: int | None = None,
) -> list[sa.ColumnElement[bool]]:
    """Return WHERE clauses for filtering pools.
    Reusable in correlated subqueries where .subquery() would break correlation.
    """
    clauses: list[sa.ColumnElement[bool]] = []

    if id is not None:
        clauses.append(Pool.id == id)
    if user_id is not None:
        clauses.append(Pool.owner_id == user_id)
    if library_id is not None:
        clauses.append(
            sa.select(1).where(
                (Library.pool_id == Pool.id) &
                (Library.id == library_id)
            ).correlate_except(Library).exists()
        )
    if experiment_id is not None:
        clauses.append(Pool.experiment_id == experiment_id)
    if seq_request_id is not None:
        clauses.append(Pool.seq_request_id == seq_request_id)
    if lab_prep_id is not None:
        clauses.append(Pool.lab_prep_id == lab_prep_id)
    if status is not None:
        clauses.append(Pool.status_id == status.id)
    if status_in is not None:
        clauses.append(Pool.status_id.in_([s.id for s in status_in]))
    if type_in is not None:
        clauses.append(Pool.type_id.in_([t.id for t in type_in]))
    if library_types_in is not None:
        clauses.append(
            sa.select(1).where(
                (Library.pool_id == Pool.id) &
                (Library.type_id.in_([lt.id for lt in library_types_in]))
            ).correlate_except(Library).exists()
        )
    if associated_to_experiment is not None:
        if associated_to_experiment:
            clauses.append(Pool.experiment_id.isnot(None))
        else:
            clauses.append(Pool.experiment_id.is_(None))

    if viewer_id is not None:
        clauses.append(access_level(viewer_id) >= AccessLevel.READ)

    return clauses