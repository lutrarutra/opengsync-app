import sqlalchemy as sa

from ..models import Library, Sample, links, Pool
from ..categories import (
    LibraryType, LibraryStatus, GenomeRef, ServiceType, IndexType, MUXType
)

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


def select(
    id: int | None = None,
    user_id: int | None = None, sample_id: int | None = None,
    experiment_id: int | None = None, seq_request_id: int | None = None,
    service_type: ServiceType | None = None,
    pool_id: int | None = None, lab_prep_id: int | None = None,
    in_lab_prep: bool | None = None,
    project_id: int | None = None,
    type_in: list[LibraryType] | None = None,
    status_in: list[LibraryStatus] | None = None,
    pooled: bool | None = None, status: LibraryStatus | None = None,
    search_name: str | None = None,
    search_pool_name: str | None = None,
    statement: sa.Select[tuple[Library]] = sa.select(Library),
) -> sa.Select[tuple[Library]]:
    if id is not None:
        statement = statement.where(Library.id == id)
    if user_id is not None:
        statement = statement.where(Library.owner_id == user_id)

    if seq_request_id is not None:
        statement = statement.where(Library.seq_request_id == seq_request_id)

    if sample_id is not None:
        statement = statement.where(
            sa.exists().where(
                (links.SampleLibraryLink.sample_id == sample_id) &
                (Library.id == links.SampleLibraryLink.library_id)
            )
        )

    if project_id is not None:
        statement = statement.where(
            sa.exists().where(
                (links.SampleLibraryLink.sample_id == Sample.id) &
                (Library.id == links.SampleLibraryLink.library_id) &
                (Sample.project_id == project_id)
            )
        )

    if experiment_id is not None:
        statement = statement.where(Library.experiment_id == experiment_id)

    if pooled is not None:
        if pooled:
            statement = statement.where(Library.pool_id.is_not(None))
        else:
            statement = statement.where(Library.pool_id.is_(None))

    if status is not None:
        statement = statement.where(Library.status_id == status.id)

    if pool_id is not None:
        statement = statement.where(Library.pool_id == pool_id)

    if service_type is not None:
        statement = statement.where(Library.service_type_id == service_type.id)

    if lab_prep_id is not None:
        statement = statement.where(Library.lab_prep_id == lab_prep_id)

    if in_lab_prep is not None:
        if in_lab_prep:
            statement = statement.where(Library.lab_prep_id != None) # noqa
        else:
            statement = statement.where(Library.lab_prep_id == None) # noqa

    if type_in is not None:
        statement = statement.where(Library.type_id.in_([t.id for t in type_in]))

    if status_in is not None:
        statement = statement.where(Library.status_id.in_([s.id for s in status_in]))

    if search_name is not None:
        statement = statement.where(Library.name.ilike(f"%{search_name}%"))
    if search_pool_name is not None:
        statement = statement.join(
            Library.pool
        ).where(Library.pool.has(Pool.name.ilike(f"%{search_pool_name}%")))

    return statement