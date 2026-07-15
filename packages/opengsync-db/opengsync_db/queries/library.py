import sqlalchemy as sa
from sqlalchemy import sql

from ..models import Library, Sample, links, Pool, User, SeqRequest
from ..categories import (
    LibraryType, LibraryStatus, GenomeRef, ServiceType, IndexType, MUXType,
    UserRole, AccessLevel, SeqRequestStatus
)
from ..core import utils

def create(
    name: str,
    sample_name: str,
    library_type: LibraryType,
    owner_id: int,
    seq_request_id: int,
    genome_ref: GenomeRef,
    service_type: ServiceType,
    clone_number: int,
    status: LibraryStatus,
    original_library_id: int | None = None,
    properties: dict | None = None,
    index_type: IndexType | None = None,
    nuclei_isolation: bool = False,
    mux_type: MUXType | None = None,
    pool_id: int | None = None,
    lab_prep_id: int | None = None,
    seq_depth_requested: float | None = None,
) -> Library:
    return Library(
        name=name.strip(),
        sample_name=sample_name,
        seq_request_id=seq_request_id,
        genome_ref_id=genome_ref.id if genome_ref is not None else None,
        type_id=library_type.id,
        service_type_id=service_type.id,
        owner_id=owner_id,
        pool_id=pool_id,
        lab_prep_id=lab_prep_id,
        status_id=status.id,
        clone_number=clone_number,
        index_type_id=index_type.id if index_type is not None else None,
        properties=properties if properties is not None and len(properties) > 0 else None,
        seq_depth_requested=seq_depth_requested,
        nuclei_isolation=nuclei_isolation,
        mux_type_id=mux_type.id if mux_type is not None else None,
        original_library_id=original_library_id,
    )


def access_level(user_id: int) -> sa.ColumnElement[AccessLevel]:
    is_admin = sa.select(1).where(User.id == user_id, User.is_admin)
    is_insider = sa.select(1).where(User.id == user_id, User.is_insider)

    has_write_access = sa.select(1).where(
        Library.seq_request_id == SeqRequest.id,
        SeqRequest.status_id == SeqRequestStatus.DRAFT.id,
        sa.or_(
            SeqRequest.requestor_id == user_id,
            sa.select(1).where(
                (links.UserAffiliation.user_id == user_id) &
                (links.UserAffiliation.group_id == SeqRequest.group_id)
            ).correlate_except(links.UserAffiliation).exists()
        )
    ).correlate_except(SeqRequest)

    has_read_access = sa.select(1).where(
        Library.seq_request_id == SeqRequest.id,
        sa.or_(
            SeqRequest.requestor_id == user_id,
            sa.select(1).where(
                (links.UserAffiliation.user_id == user_id) &
                (links.UserAffiliation.group_id == SeqRequest.group_id)
            ).correlate_except(links.UserAffiliation).exists()
        )
    ).correlate_except(SeqRequest)

    return sa.case(
        (sa.exists(is_admin), AccessLevel.ADMIN),
        (sa.exists(is_insider), AccessLevel.INSIDER),
        (sa.exists(has_write_access), AccessLevel.WRITE),
        (sa.exists(has_read_access), AccessLevel.READ),
        else_=AccessLevel.NONE
    )

def search(
    name: str | None = None,
    pool_name: str | None = None,
    name_weight: float = 0.5,
    pool_name_weight: float = 0.5,
    statement: sa.Select[tuple[Library]] = sa.select(Library),
) -> sa.Select[tuple[Library]]:
    filter_conditions: list[sql.ColumnElement[bool]] = []
    relevance = sa.literal(0.0)

    if name is not None:
        filter_conditions.append(utils.safe_trgm_search(Library.name, name))
        relevance += sa.func.similarity(Library.name, name) * name_weight

    if pool_name is not None:
        filter_conditions.append(utils.safe_trgm_search(Pool.name, pool_name))
        relevance += sa.func.similarity(Pool.name, pool_name) * pool_name_weight

    if not filter_conditions:
        return statement

    statement = statement.where(sa.or_(*filter_conditions))

    if pool_name is not None:
        statement = statement.join(Pool, Library.pool_id == Pool.id)

    return statement.order_by(sa.nulls_last(relevance.desc()))


def select(
    id: int | None = None,
    ids: list[int] | None = None,
    user_id: int | None = None,
    sample_id: int | None = None,
    experiment_id: int | None = None,
    seq_request_id: int | None = None,
    service_type: ServiceType | None = None,
    pool_id: int | None = None,
    lab_prep_id: int | None = None,
    in_lab_prep: bool | None = None,
    project_id: int | None = None,
    type_in: list[LibraryType] | None = None,
    status_in: list[LibraryStatus] | None = None,
    pooled: bool | None = None,
    indexed: bool | None = None,
    status: LibraryStatus | None = None,
    viewer_id: int | None = None,
    statement: sa.Select[tuple[Library]] = sa.select(Library),
) -> sa.Select[tuple[Library]]:
    return statement.where(*where_clauses(
        id=id,
        ids=ids,
        user_id=user_id,
        sample_id=sample_id,
        experiment_id=experiment_id,
        seq_request_id=seq_request_id,
        service_type=service_type,
        pool_id=pool_id,
        lab_prep_id=lab_prep_id,
        in_lab_prep=in_lab_prep,
        project_id=project_id,
        type_in=type_in,
        status_in=status_in,
        pooled=pooled,
        status=status,
        indexed=indexed,
        viewer_id=viewer_id,
    ))

def permissions(library_id: int, user_id: int) -> sa.Select[tuple[AccessLevel]]:
    return sa.select(access_level(user_id)).where(Library.id == library_id)


def where_clauses(
    id: int | None = None,
    ids: list[int] | None = None,
    user_id: int | None = None,
    sample_id: int | None = None,
    experiment_id: int | None = None,
    seq_request_id: int | None = None,
    service_type: ServiceType | None = None,
    pool_id: int | None = None,
    lab_prep_id: int | None = None,
    in_lab_prep: bool | None = None,
    project_id: int | None = None,
    type_in: list[LibraryType] | None = None,
    status_in: list[LibraryStatus] | None = None,
    pooled: bool | None = None,
    indexed: bool | None = None,
    status: LibraryStatus | None = None,
    viewer_id: int | None = None,
) -> list[sa.ColumnElement[bool]]:
    """Return WHERE clauses for filtering libraries.
    Reusable in correlated subqueries where .subquery() would break correlation.
    """
    clauses: list[sa.ColumnElement[bool]] = []

    if id is not None:
        clauses.append(Library.id == id)
    if ids:
        clauses.append(Library.id.in_(ids))
    if user_id is not None:
        clauses.append(Library.owner_id == user_id)
    if seq_request_id is not None:
        clauses.append(Library.seq_request_id == seq_request_id)
    if sample_id is not None:
        clauses.append(
            sa.select(1).where(
                (links.SampleLibraryLink.sample_id == sample_id),
                (Library.id == links.SampleLibraryLink.library_id)
            ).correlate_except(links.SampleLibraryLink).exists()
        )
    if project_id is not None:
        clauses.append(
            sa.select(1).where(
                (links.SampleLibraryLink.sample_id == Sample.id),
                (Library.id == links.SampleLibraryLink.library_id),
                (Sample.project_id == project_id)
            ).correlate_except(Sample, links.SampleLibraryLink).exists()
        )
    if experiment_id is not None:
        clauses.append(Library.experiment_id == experiment_id)
    if pooled is not None:
        if pooled:
            clauses.append(Library.pool_id.is_not(None))
        else:
            clauses.append(Library.pool_id.is_(None))
    if indexed is not None:
        if indexed:
            clauses.append(Library.is_indexed.is_(True))
        else:
            clauses.append(Library.is_indexed.is_(False))
    if status is not None:
        clauses.append(Library.status_id == status.id)
    if pool_id is not None:
        clauses.append(Library.pool_id == pool_id)
    if service_type is not None:
        clauses.append(Library.service_type_id == service_type.id)
    if lab_prep_id is not None:
        clauses.append(Library.lab_prep_id == lab_prep_id)
    if in_lab_prep is not None:
        if in_lab_prep:
            clauses.append(Library.lab_prep_id != None)  # noqa
        else:
            clauses.append(Library.lab_prep_id == None)  # noqa
    if type_in is not None:
        clauses.append(Library.type_id.in_([t.id for t in type_in]))
    if status_in is not None:
        clauses.append(Library.status_id.in_([s.id for s in status_in]))
    if viewer_id is not None:
        clauses.append(access_level(viewer_id) >= AccessLevel.READ)
    return clauses