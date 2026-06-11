import sqlalchemy as sa

from ..models import (
    Experiment, Project, Sample, Library, LibraryIndex, Pool, Lane, User,
    SeqRequest, Contact, IndexKit, Barcode, Feature, FeatureKit,
    Protocol, Kit, Plate, SeqQuality, PoolDilution, links,
)
from ..categories import LibraryType


# ---------------------------------------------------------------------------
# Experiment queries
# ---------------------------------------------------------------------------

def experiment_libraries(
    experiment_id: int,
    include_sample: bool = False,
    include_index_kit: bool = False,
    include_seq_request: bool = False,
    include_indices: bool = False,
) -> sa.Select:
    columns = [
        Experiment.id.label("experiment_id"), Experiment.name.label("experiment_name"),
        Lane.number.label("lane"), Pool.id.label("pool_id"), Pool.name.label("pool_name"),
        Library.id.label("library_id"), Library.name.label("library_name"), Library.type_id.label("library_type_id"),
        Library.genome_ref_id.label("reference_id"), Library.sample_name.label("sample_name"),
        Library.mux_type_id.label("mux_type_id"),
    ]

    if include_indices:
        columns.extend([
            LibraryIndex.sequence_i7.label("sequence_i7"), LibraryIndex.sequence_i5.label("sequence_i5"),
            LibraryIndex.name_i7.label("name_i7"), LibraryIndex.name_i5.label("name_i5"),
        ])

    if include_seq_request:
        columns.extend([
            SeqRequest.id.label("seq_request_id"), SeqRequest.name.label("request_name"),
            User.id.label("requestor_id"), User.email.label("requestor_email"),
        ])

    if include_index_kit:
        columns.extend([
            IndexKit.id.label("index_kit_id"), IndexKit.name.label("index_kit_name"),
        ])

    if include_sample:
        columns.extend([
            Sample.id.label("sample_id"), Sample.name.label("sample_name"),
        ])

    query = sa.select(*columns).where(
        Experiment.id == experiment_id
    ).join(
        Lane,
        Lane.experiment_id == Experiment.id
    ).join(
        links.LanePoolLink,
        links.LanePoolLink.lane_id == Lane.id
    ).join(
        Pool,
        Pool.id == links.LanePoolLink.pool_id
    ).join(
        Library,
        Library.pool_id == Pool.id
    )

    if include_indices:
        query = query.join(
            LibraryIndex,
            LibraryIndex.library_id == Library.id,
        )

    if include_sample:
        query = query.join(
            links.SampleLibraryLink,
            links.SampleLibraryLink.library_id == Library.id,
        ).join(
            Sample,
            Sample.id == links.SampleLibraryLink.sample_id,
        )

    if include_seq_request:
        query = query.join(
            SeqRequest,
            SeqRequest.id == Library.seq_request_id,
        ).join(
            User,
            User.id == SeqRequest.requestor_id,
        )

    query = query.order_by(Lane.number, Pool.id, Library.id)
    return query


def flowcell(experiment_id: int | str) -> sa.Select:
    columns = [
        Experiment.id.label("experiment_id"), Experiment.name.label("experiment_name"),
        Lane.number.label("lane"),
        Pool.id.label("pool_id"), Pool.name.label("pool_name"),
        Library.sample_name.label("sample_name"),
        Library.id.label("library_id"), Library.name.label("library_name"),
        Library.type_id.label("library_type_id"),
        Library.genome_ref_id.label("reference_id"),
        Library.seq_request_id.label("seq_request_id"),
        LibraryIndex.sequence_i7.label("sequence_i7"), LibraryIndex.sequence_i5.label("sequence_i5"),
        LibraryIndex.name_i7.label("name_i7"), LibraryIndex.name_i5.label("name_i5"),
        LibraryIndex._orientation.label("orientation_id"),
        Protocol.read_structure.label("read_structure"), Protocol.name.label("protocol_name"),
    ]

    query = sa.select(*columns).where(
        (Experiment.id == experiment_id) if isinstance(experiment_id, int) else (Experiment.name == experiment_id)
    ).join(
        Lane,
        Lane.experiment_id == Experiment.id,
    ).join(
        links.LanePoolLink,
        links.LanePoolLink.lane_id == Lane.id
    ).join(
        Pool,
        Pool.id == links.LanePoolLink.pool_id
    ).join(
        Library,
        Library.pool_id == Pool.id,
    ).join(
        LibraryIndex,
        LibraryIndex.library_id == Library.id,
        isouter=True
    ).join(
        Protocol,
        Protocol.id == Library.protocol_id,
        isouter=True
    )

    query = query.order_by(Lane.number, Pool.id, Library.id)
    return query


def experiment_barcodes(experiment_id: int) -> sa.Select:
    query = sa.select(
        Lane.id.label("lane_id"), Lane.number.label("lane"),
        Library.id.label("library_id"), Library.name.label("library_name"), Library.sample_name.label("sample_name"),
        Pool.id.label("pool_id"), Pool.name.label("pool_name"),
        LibraryIndex.sequence_i7.label("sequence_i7"), LibraryIndex.sequence_i5.label("sequence_i5"),
        LibraryIndex.name_i7.label("name_i7"), LibraryIndex.name_i5.label("name_i5"),
        LibraryIndex._orientation.label("orientation_id"),
        LibraryIndex.index_kit_i7_id.label("kit_i7_id"),
        LibraryIndex.index_kit_i5_id.label("kit_i5_id"),
    ).where(
        Lane.experiment_id == experiment_id
    ).join(
        links.LanePoolLink,
        links.LanePoolLink.lane_id == Lane.id
    ).join(
        Pool,
        Pool.id == links.LanePoolLink.pool_id
    ).join(
        Library,
        Library.pool_id == Pool.id
    ).join(
        LibraryIndex,
        LibraryIndex.library_id == Library.id
    )

    return query


def experiment_pools(experiment_id: int) -> sa.Select:
    query = sa.select(
        Pool.id, Pool.name, Pool.status_id,
        Pool.num_m_reads_requested, Pool.qubit_concentration,
        Pool.avg_fragment_size,
    ).where(
        Pool.experiment_id == experiment_id
    )

    return query


def experiment_lanes(experiment_id: int) -> sa.Select:
    query = sa.select(
        Lane.id, Lane.number.label("lane"),
        Lane.phi_x, Lane.original_qubit_concentration, Lane.total_volume_ul,
        Lane.library_volume_ul, Lane.avg_fragment_size, Lane.sequencing_qubit_concentration,
        Lane.target_molarity, Lane.lane_molarity, Lane.sequencing_molarity,
    ).where(
        Lane.experiment_id == experiment_id
    ).order_by(Lane.number)

    return query


def experiment_laned_pools(experiment_id: int) -> sa.Select:
    query = sa.select(
        Lane.id.label("lane_id"), Lane.number.label("lane"),
        Pool.id.label("pool_id"), Pool.name.label("pool_name"),
        Pool.num_m_reads_requested, Pool.qubit_concentration,
        Pool.avg_fragment_size, links.LanePoolLink.num_m_reads,
        PoolDilution.id.label("dilution_id"), PoolDilution.identifier.label("dilution"),
    ).where(
        Lane.experiment_id == experiment_id
    ).join(
        links.LanePoolLink,
        links.LanePoolLink.lane_id == Lane.id
    ).join(
        Pool,
        Pool.id == links.LanePoolLink.pool_id
    ).join(
        PoolDilution,
        PoolDilution.id == links.LanePoolLink.dilution_id,
        isouter=True
    )

    return query


def experiment_seq_qualities(experiment_id: int) -> sa.Select:
    query = sa.select(
        Library.id.label("library_id"), Library.name.label("library_name"),
        SeqQuality.lane, SeqQuality.num_reads, SeqQuality.qc
    ).where(
        SeqQuality.experiment_id == experiment_id
    ).join(
        Library,
        Library.id == SeqQuality.library_id,
        isouter=True
    )

    return query


def experiment_stats(experiment_id: int) -> sa.Select:
    query = sa.select(
        SeqQuality.lane.label("lane"),
        SeqQuality.num_reads.label("num_reads"),
        SeqQuality.qc.label("qc"),
        Library.id.label("library_id"),
        Library.name.label("library_name"),
        Pool.id.label("pool_id"),
        Pool.name.label("pool_name"),
    ).where(
        SeqQuality.experiment_id == experiment_id
    ).join(
        Library,
        Library.id == SeqQuality.library_id,
        isouter=True
    ).join(
        Pool,
        Pool.id == Library.pool_id,
        isouter=True
    ).order_by(
        SeqQuality.lane
    )

    return query


# ---------------------------------------------------------------------------
# Project queries
# ---------------------------------------------------------------------------

def project_crispr_guides(project_id: int) -> sa.Select:
    query = sa.select(
        Library.id.label("library_id"),
        Library.name.label("library_name"),
        Library.sample_name.label("sample_pool"),
        Library.properties.label("properties"),
    ).where(
        sa.select(1).where(
            (links.SampleLibraryLink.sample_id == Sample.id) &
            (Library.id == links.SampleLibraryLink.library_id) &
            (Sample.project_id == project_id)
        ).correlate_except(Sample, links.SampleLibraryLink).exists(),
        Library.type_id == LibraryType.PARSE_SC_CRISPR.id
    )

    return query


def project_features(project_id: int) -> sa.Select:
    query = sa.select(
        Feature.name.label("feature"), Feature.identifier.label("identifier"),
        Feature.sequence.label("sequence"), Feature.pattern.label("pattern"), Feature.read.label("read"),
        Feature.type_id.label("type_id"), Feature.target_name.label("target_name"), Feature.target_id.label("target_id"),
        Library.sample_name.label("sample_pool"),
        FeatureKit.identifier.label("kit")
    ).where(
        sa.select(1).where(
            (links.SampleLibraryLink.sample_id == Sample.id) &
            (Library.id == links.SampleLibraryLink.library_id) &
            (Sample.project_id == project_id) &
            (Library.type_id.in_([
                LibraryType.TENX_SC_ABC_FLEX.id,
                LibraryType.TENX_ANTIBODY_CAPTURE.id
            ]))
        ).correlate_except(Sample, links.SampleLibraryLink).exists()
    ).join(
        links.LibraryFeatureLink,
        links.LibraryFeatureLink.library_id == Library.id
    ).join(
        Feature,
        Feature.id == links.LibraryFeatureLink.feature_id
    ).outerjoin(
        FeatureKit,
        FeatureKit.id == Feature.feature_kit_id,
    )

    return query


def project_samples(project_id: int, with_libraries: bool = False) -> sa.Select:
    cols = [
        Sample.id.label("sample_id"),
        Sample.name.label("sample_name"),
        Sample._attributes.label("attributes"),
    ]
    if with_libraries:
        cols.extend([
            Library.id.label("library_id"),
            Library.name.label("library_name"),
            Library.sample_name.label("sample_pool"),
            Library.type_id.label("library_type_id"),
            Library.genome_ref_id.label("genome_ref_id"),
            Library.seq_request_id.label("seq_request_id"),
        ])

    query = sa.select(*cols).where(Sample.project_id == project_id)

    if with_libraries:
        query = query.join(
            links.SampleLibraryLink,
            links.SampleLibraryLink.sample_id == Sample.id,
        ).join(
            Library,
            Library.id == links.SampleLibraryLink.library_id,
        )

    return query


def project_seq_requests(project_id: int) -> sa.Select:
    query = sa.select(
        SeqRequest.id.label("seq_request_id"),
        SeqRequest.name.label("seq_request_name"),
        SeqRequest.status_id.label("status_id"),
        Contact.name.label("contact_name"),
        Contact.email.label("contact_email"),
        Contact.phone.label("contact_phone"),
    )

    query = query.where(
        sa.select(1).where(
            (Sample.project_id == Project.id) &
            (links.SampleLibraryLink.sample_id == Sample.id) &
            (Library.id == links.SampleLibraryLink.library_id) &
            (Library.seq_request_id == SeqRequest.id) &
            (Project.id == project_id)
        ).correlate_except(Sample, links.SampleLibraryLink, Library, Project).exists()
    )
    query = query.join(
        Contact,
        Contact.id == SeqRequest.contact_person_id,
    )

    return query


def project_libraries_libraries(project_id: int) -> sa.Select:
    """First query for project_libraries: fetches library metadata."""
    query = sa.select(
        Library.experiment_id.label("experiment_id"),
        Library.id.label("library_id"),
        Library.name.label("library_name"),
        Library.sample_name.label("sample_pool"),
        Library.type_id.label("library_type_id"),
        Library.genome_ref_id.label("genome_ref_id"),
        Library.seq_request_id.label("seq_request_id"),
        Library.properties.label("properties"),

        Sample.id.label("sample_id"),
        Sample.name.label("sample_name"),

        links.SampleLibraryLink.mux.label("mux"),
        Library.mux_type_id.label("mux_type_id"),
    ).where(
        Sample.project_id == project_id
    ).join(
        links.SampleLibraryLink,
        links.SampleLibraryLink.sample_id == Sample.id
    ).join(
        Library,
        Library.id == links.SampleLibraryLink.library_id
    )

    return query


def project_libraries_lanes(experiment_ids: list[int], library_ids: list[int]) -> sa.Select:
    """Second query for project_libraries: fetches lane/pool info."""
    query = sa.select(
        Experiment.id.label("experiment_id"), Experiment.name.label("experiment_name"),
        Lane.number.label("lane"), Pool.id.label("pool_id"), Pool.name.label("pool_name"),
        Library.id.label("library_id")
    ).where(
        sa.and_(Experiment.id.in_(experiment_ids), Library.id.in_(library_ids))
    ).join(
        Lane,
        Lane.experiment_id == Experiment.id
    ).join(
        links.LanePoolLink,
        links.LanePoolLink.lane_id == Lane.id
    ).join(
        Pool,
        Pool.id == links.LanePoolLink.pool_id
    ).join(
        Library,
        Library.pool_id == Pool.id
    )

    return query


def project_latest_request_share_emails(project_id: int) -> sa.Select:
    query = sa.select(
        links.SeqRequestDeliveryEmailLink.seq_request_id.label("seq_request_id"),
        links.SeqRequestDeliveryEmailLink.email.label("email"),
        links.SeqRequestDeliveryEmailLink.status_id.label("status_id"),
    ).where(
        links.SeqRequestDeliveryEmailLink.seq_request_id == sa.select(
            sa.func.max(SeqRequest.id)
        ).where(
            sa.select(1).where(
                (Sample.project_id == project_id) &
                (links.SampleLibraryLink.sample_id == Sample.id) &
                (Library.id == links.SampleLibraryLink.library_id) &
                (Library.seq_request_id == SeqRequest.id)
            ).correlate_except(Sample, links.SampleLibraryLink, Library).exists()
        ).scalar_subquery()
    )

    return query


# ---------------------------------------------------------------------------
# Library queries
# ---------------------------------------------------------------------------

def library_features(library_id: int) -> sa.Select:
    query = sa.select(
        Feature.id.label("feature_id"), Feature.name.label("feature_name"), Feature.type_id.label("feature_type_id"),
        Feature.identifier.label("identifier"),
        Feature.target_id.label("target_id"), Feature.target_name.label("target_name"),
        Feature.sequence.label("sequence"), Feature.pattern.label("pattern"), Feature.read.label("read"),
        FeatureKit.id.label("feature_kit_id"), FeatureKit.identifier.label("kit_identifier"), FeatureKit.name.label("feature_kit_name"),
    ).join(
        FeatureKit,
        FeatureKit.id == Feature.feature_kit_id,
        isouter=True
    ).join(
        links.LibraryFeatureLink,
        links.LibraryFeatureLink.feature_id == Feature.id
    ).where(
        links.LibraryFeatureLink.library_id == library_id
    ).distinct()

    return query


def library_samples(library_id: int) -> sa.Select:
    query = sa.select(
        Sample.id.label("sample_id"), Sample.name.label("sample_name"), Sample._attributes.label("attributes"),
    ).join(
        links.SampleLibraryLink,
        links.SampleLibraryLink.sample_id == Sample.id
    ).where(
        links.SampleLibraryLink.library_id == library_id
    )

    return query


def library_mux_table(library_id: int) -> sa.Select:
    query = sa.select(
        links.SampleLibraryLink.sample_id.label("sample_id"), Sample.name.label("sample_name"),
        links.SampleLibraryLink.mux.label("mux"),
    ).join(
        Sample,
        Sample.id == links.SampleLibraryLink.sample_id
    ).where(
        links.SampleLibraryLink.library_id == library_id
    )

    return query


def library_properties(
    project_id: int | None = None,
    seq_request_id: int | None = None,
) -> sa.Select:
    query = sa.select(
        Library.id.label("library_id"),
        Library.name.label("library_name"),
        Library.properties.label("properties"),
    )

    if seq_request_id is not None:
        query = query.where(
            Library.seq_request_id == seq_request_id
        )
    else:
        query = query.join(
            links.SampleLibraryLink,
            links.SampleLibraryLink.library_id == Library.id
        ).join(
            Sample,
            Sample.id == links.SampleLibraryLink.sample_id
        ).where(
            Sample.project_id == project_id
        )

    return query


def library_stats(library_id: int) -> sa.Select:
    query = sa.select(
        SeqQuality.lane.label("lane"),
        SeqQuality.num_reads.label("num_reads"),
        SeqQuality.qc.label("qc"),
    ).where(
        SeqQuality.library_id == library_id
    ).order_by(
        SeqQuality.lane
    )

    return query


def library_data_qc(library_id: int | None = None) -> sa.Select:
    query = sa.select(
        Library.name.label("library_name"),
        Library.type_id.label("library_type_id"),
        Library.id.label("library_id"),
        Library.qc,
        Pool.type_id.label("pool_type_id"),
    ).where(
        Library.qc.isnot(None)
    ).join(
        Pool,
        Pool.id == Library.pool_id,
    )

    if library_id is not None:
        query = query.where(Library.id == library_id)

    return query


def library_sample_pool(library_id: int) -> sa.Select:
    query = sa.select(
        Sample.id.label("sample_id"),
        Sample.name.label("sample_name"),
        Library.id.label("library_id"),
        Library.name.label("library_name"),
        Library.type_id.label("library_type_id"),
        Library.sample_name.label("sample_pool"),
        links.SampleLibraryLink.mux.label("mux"),
        Library.mux_type_id.label("mux_type_id"),
    ).join(
        links.SampleLibraryLink,
        links.SampleLibraryLink.library_id == Library.id
    ).join(
        Sample,
        Sample.id == links.SampleLibraryLink.sample_id
    ).where(
        Sample.id.in_(
            sa.select(links.SampleLibraryLink.sample_id).where(
                links.SampleLibraryLink.library_id == library_id
            )
        )
    )

    return query


# ---------------------------------------------------------------------------
# SeqRequest queries
# ---------------------------------------------------------------------------

def seq_requestor(seq_request_id: int) -> sa.Select:
    query = sa.select(
        SeqRequest.name.label("seq_request_name"),
        User.id.label("user_id"), User.email.label("email"),
        User.first_name.label("first_name"), User.last_name.label("last_name"),
        User.role_id.label("role_id")
    ).join(
        User,
        User.id == SeqRequest.requestor_id,
    ).where(
        SeqRequest.id == seq_request_id
    )

    return query


def seq_request_libraries(
    seq_request_id: int,
    include_indices: bool = False,
) -> sa.Select:
    columns = [
        SeqRequest.id.label("seq_request_id"),
        Library.id.label("library_id"), Library.name.label("library_name"), Library.type_id.label("library_type_id"),
        Library.genome_ref_id.label("genome_ref_id"),
        Pool.id.label("pool_id"), Pool.name.label("pool_name"),
    ]

    if include_indices:
        columns.extend([
            LibraryIndex.sequence_i7.label("sequence_i7"), LibraryIndex.sequence_i5.label("sequence_i5"),
            LibraryIndex.name_i7.label("name_i7"), LibraryIndex.name_i5.label("name_i5"),
        ])

    query = sa.select(*columns).where(
        SeqRequest.id == seq_request_id
    ).join(
        Library,
        Library.seq_request_id == SeqRequest.id
    ).join(
        Pool,
        Pool.id == Library.pool_id
    )

    if include_indices:
        query = query.join(
            LibraryIndex,
            LibraryIndex.library_id == Library.id,
        )

    query = query.order_by(Library.id)

    return query


def seq_request_samples(seq_request_id: int) -> sa.Select:
    query = sa.select(
        SeqRequest.id.label("seq_request_id"),
        Sample.id.label("sample_id"), Sample.name.label("sample_name"),
        links.SampleLibraryLink.mux.label("mux"),
        Library.id.label("library_id"), Library.name.label("library_name"), Library.type_id.label("library_type_id"),
        Library.mux_type_id.label("mux_type_id"),
        Library.genome_ref_id.label("genome_ref_id"),
        Pool.id.label("pool_id"), Pool.name.label("pool_name"),
    ).where(
        SeqRequest.id == seq_request_id
    ).join(
        Library,
        Library.seq_request_id == SeqRequest.id
    ).join(
        Pool,
        Pool.id == Library.pool_id,
        isouter=True
    ).join(
        links.SampleLibraryLink,
        links.SampleLibraryLink.library_id == Library.id,
    ).join(
        Sample,
        Sample.id == links.SampleLibraryLink.sample_id,
    )

    query = query.order_by(Library.id)

    return query


def seq_request_sample_table(seq_request_id: int) -> sa.Select:
    query = sa.select(
        Sample.id.label("sample_id"), Sample.name.label("sample_name"),
        Project.identifier.label("project_identifier"), Project.title.label("project_title"),
        Sample._attributes.label("attributes"),
    ).where(
        sa.select(1).where(
            (links.SampleLibraryLink.sample_id == Sample.id) &
            (Library.id == links.SampleLibraryLink.library_id) &
            (Library.seq_request_id == seq_request_id)
        ).correlate_except(links.SampleLibraryLink, Library).exists()
    ).join(
        Project,
        Project.id == Sample.project_id,
    )

    return query


def seq_request_features(seq_request_id: int) -> sa.Select:
    query = sa.select(
        Library.id.label("library_id"), Library.name.label("library_name"),
        Library.sample_name.label("sample_pool"),
        Feature.id.label("feature_id"), Feature.name.label("feature_name"),
        Feature.sequence.label("sequence"), Feature.pattern.label("pattern"), Feature.read.label("read"),
        Feature.type_id.label("type_id"), Feature.target_name.label("target_name"), Feature.target_id.label("target_id"),
    )

    query = query.where(
        Library.seq_request_id == seq_request_id
    ).join(
        links.LibraryFeatureLink,
        links.LibraryFeatureLink.library_id == Library.id
    ).join(
        Feature,
        Feature.id == links.LibraryFeatureLink.feature_id
    )

    return query


def seq_request_share_emails(seq_request_id: int) -> sa.Select:
    query = sa.select(
        links.SeqRequestDeliveryEmailLink.email.label("email"),
        links.SeqRequestDeliveryEmailLink.status_id.label("status_id"),
    ).where(
        links.SeqRequestDeliveryEmailLink.seq_request_id == seq_request_id
    )

    return query


# ---------------------------------------------------------------------------
# Pool queries
# ---------------------------------------------------------------------------

def pool_libraries(pool_id: int) -> sa.Select:
    columns = [
        Pool.id.label("pool_id"), Pool.name.label("pool"),
        Library.id.label("library_id"), Library.name.label("library_name"),
        Library.index_type_id.label("index_type_id"),
    ]
    query = sa.select(*columns).where(
        Pool.id == pool_id
    ).join(
        Library,
        Library.pool_id == Pool.id
    )

    query = query.order_by(Library.id)
    return query


def pool_barcodes(pool_id: int) -> sa.Select:
    columns = [
        Pool.id.label("pool_id"), Pool.name.label("pool"),
        Library.id.label("library_id"), Library.name.label("library_name"),
        Library.index_type_id.label("index_type_id"),
        LibraryIndex.name_i7.label("name_i7"), LibraryIndex.name_i5.label("name_i5"),
        LibraryIndex.sequence_i7.label("sequence_i7"), LibraryIndex.sequence_i5.label("sequence_i5"),
        LibraryIndex.index_kit_i7_id.label("kit_i7_id"), LibraryIndex.index_kit_i5_id.label("kit_i5_id"),
    ]
    query = sa.select(*columns).where(
        Pool.id == pool_id
    ).join(
        Library,
        Library.pool_id == Pool.id
    ).join(
        LibraryIndex,
        LibraryIndex.library_id == Library.id,
        isouter=True
    )

    query = query.order_by(Library.id)
    return query


def pool_num_reads_stats_sequenced(experiment_id: int) -> sa.Select:
    """First query for pool_num_reads_stats: fetches actual sequenced reads per pool."""
    query = sa.select(
        Pool.id.label("pool_id"),
        Pool.name.label("pool_name"),
        Pool.num_m_reads_requested.label("num_m_reads_requested"),
        SeqQuality.num_reads.label("num_reads"),
    ).where(
        SeqQuality.experiment_id == experiment_id
    ).join(
        Library,
        Library.id == SeqQuality.library_id,
        isouter=True
    ).join(
        Pool,
        Pool.id == Library.pool_id,
        isouter=True
    )

    return query


def pool_num_reads_stats_planned(experiment_id: int) -> sa.Select:
    """Second query for pool_num_reads_stats: fetches planned reads per pool."""
    query = sa.select(
        links.LanePoolLink.pool_id.label("pool_id"),
        links.LanePoolLink.num_m_reads.label("num_m_reads"),
    ).where(
        links.LanePoolLink.experiment_id == experiment_id
    )

    return query


# ---------------------------------------------------------------------------
# Kit queries
# ---------------------------------------------------------------------------

def index_kit_barcodes(index_kit_id: int) -> sa.Select:
    query = sa.select(
        Barcode.id, Barcode.sequence.label("sequence"), Barcode.well.label("well"),
        Barcode.name.label("name"), Barcode.adapter_id.label("adapter_id"),
        Barcode.type_id.label("type_id"),
    ).where(
        Barcode.index_kit_id == index_kit_id
    )

    return query


def feature_kit_features(feature_kit_id: int) -> sa.Select:
    query = sa.select(
        Feature.id.label("feature_id"), Feature.name.label("name"), Feature.identifier.label("identifier"),
        Feature.sequence.label("sequence"), Feature.pattern.label("pattern"), Feature.read.label("read"),
        Feature.type_id.label("type_id"),
        Feature.target_name.label("target_name"), Feature.target_id.label("target_id"),
    ).where(
        Feature.feature_kit_id == feature_kit_id
    )

    return query


def protocol_kits(protocol_id: int | None = None) -> sa.Select:
    query = sa.select(
        links.ProtocolKitLink.protocol_id.label("protocol_id"),
        Kit.id.label("kit_id"),
        Kit.name.label("kit_name"),
        Kit.identifier.label("kit_identifier"),
        links.ProtocolKitLink.combination_num,
    )

    if protocol_id is not None:
        query = query.where(
            links.ProtocolKitLink.protocol_id == protocol_id
        )

    query = query.join(
        Kit,
        Kit.id == links.ProtocolKitLink.kit_id
    )

    return query


# ---------------------------------------------------------------------------
# Plate queries
# ---------------------------------------------------------------------------

def plate(plate_id: int) -> sa.Select:
    query = sa.select(
        Plate.id, Plate.name, links.SamplePlateLink.well_idx,
        links.SamplePlateLink.sample_id, links.SamplePlateLink.library_id,
        Sample.name.label("sample_name"), Library.name.label("library_name"),
    ).where(
        Plate.id == plate_id
    ).join(
        links.SamplePlateLink,
        links.SamplePlateLink.plate_id == Plate.id
    ).join(
        Sample,
        Sample.id == links.SamplePlateLink.sample_id,
        isouter=True
    ).join(
        Library,
        Library.id == links.SamplePlateLink.library_id,
        isouter=True
    )

    return query


# ---------------------------------------------------------------------------
# Lab prep queries
# ---------------------------------------------------------------------------

def lab_prep_libraries(lab_prep_id: int) -> sa.Select:
    query = sa.select(
        Library.id.label("library_id"),
        Library.name.label("library_name"),
        Library.status_id.label("status_id"),
        Library.type_id.label("library_type_id"),
        Library.genome_ref_id.label("genome_ref_id"),
        Pool.id.label("pool_id"), Pool.name.label("pool"),
        Library.index_type_id.label("index_type_id"),
    ).where(
        Library.lab_prep_id == lab_prep_id
    ).outerjoin(
        Pool,
        Pool.id == Library.pool_id
    )

    return query


def lab_prep_barcodes(lab_prep_id: int) -> sa.Select:
    query = sa.select(
        Library.sample_name.label("sample_name"),
        Library.id.label("library_id"), Library.name.label("library_name"),
        Library.type_id.label("library_type_id"),
        Library.genome_ref_id.label("reference_id"),
        Library.seq_request_id.label("seq_request_id"),
        Library.index_type_id.label("index_type_id"),
        LibraryIndex.name_i7.label("name_i7"), LibraryIndex.name_i5.label("name_i5"),
        LibraryIndex.index_kit_i7_id.label("kit_i7_id"), LibraryIndex.index_kit_i5_id.label("kit_i5_id"),
        LibraryIndex.sequence_i7.label("sequence_i7"), LibraryIndex.sequence_i5.label("sequence_i5"),
        Pool.id.label("pool_id"), Pool.name.label("pool"),
    ).where(
        Library.lab_prep_id == lab_prep_id
    ).join(
        Pool,
        Pool.id == Library.pool_id,
        isouter=True
    ).join(
        LibraryIndex,
        LibraryIndex.library_id == Library.id,
        isouter=True
    )

    return query


def lab_prep_pooling_table(lab_prep_id: int) -> sa.Select:
    query = sa.select(
        Library.id.label("library_id"), Library.name.label("library_name"),
        Library.type_id.label("library_type_id"), Library.sample_name.label("sample_pool"),
        Library.mux_type_id.label("mux_type_id"),
        Sample.id.label("sample_id"), Sample.name.label("sample_name"),
        links.SampleLibraryLink.mux.label("mux"),
    ).where(
        Library.lab_prep_id == lab_prep_id
    ).join(
        links.SampleLibraryLink,
        links.SampleLibraryLink.library_id == Library.id
    ).join(
        Sample,
        Sample.id == links.SampleLibraryLink.sample_id,
    )

    return query


# ---------------------------------------------------------------------------
# Barcode queries
# ---------------------------------------------------------------------------

def query_barcode_sequences(sequence: str, limit: int = 10) -> sa.Select:
    query = sa.select(
        Barcode.id.label("id"), Barcode.sequence.label("sequence"),
        Barcode.well.label("well"), Barcode.name.label("name"),
        Barcode.type_id.label("type_id"),
        IndexKit.id.label("kit_id"), IndexKit.name.label("kit_name"),
        IndexKit.identifier.label("kit_identifier"),
    ).join(
        IndexKit,
        IndexKit.id == Barcode.index_kit_id
    )

    query = query.order_by(
        sa.func.similarity(Barcode.sequence, sequence).desc()
    ).limit(limit)

    return query


def match_barcodes_to_kit(
    unique_sequences: list[str],
    num_sequences: int,
    barcode_type_id: int,
    index_type_id: int | None = None,
) -> sa.Select:
    # Subquery to find IDs of kits that contain all requested sequences
    matched_kits_query = (
        sa.select(Barcode.index_kit_id)
        .where(
            Barcode.type_id == barcode_type_id,
            Barcode.sequence.in_(unique_sequences)
        )
        .group_by(Barcode.index_kit_id)
        .having(sa.func.count(sa.distinct(Barcode.sequence)) == num_sequences)
    ).scalar_subquery()

    # Final query to fetch kit metadata for those IDs
    query = sa.select(
        IndexKit.id.label("kit_id"),
        IndexKit.name.label("kit_name"),
        IndexKit.identifier.label("kit_identifier"),
    ).where(
        IndexKit.id.in_(matched_kits_query),
    )
    if index_type_id is not None:
        query = query.where(
            IndexKit.type_id == index_type_id
        )

    return query
