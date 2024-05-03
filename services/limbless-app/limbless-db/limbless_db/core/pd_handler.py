import pandas as pd

import sqlalchemy as sa
from sqlalchemy.sql.operators import and_  # noqa: F401

from .. import models
from .. import categories


def get_experiment_libraries_df(
    self, experiment_id: int,
    include_sample: bool = False, include_index_kit: bool = False,
    include_visium: bool = False, include_seq_request: bool = False,
    collapse_lanes: bool = True
) -> pd.DataFrame:
        
    columns = [
        models.Library.id.label("library_id"), models.Library.name.label("library_name"), models.Library.type_id.label("library_type_id"),
        models.Library.genome_ref_id.label("reference_id"),
        models.Library.adapter, models.Library.index_1_sequence.label("index_1"), models.Library.index_2_sequence.label("index_2"),
        models.Library.index_3_sequence.label("index_3"), models.Library.index_4_sequence.label("index_4"),
        models.Pool.id.label("pool_id"), models.Pool.name.label("pool_name"), models.Lane.number.label("lane"),
    ]
    if include_seq_request:
        columns.extend([
            models.SeqRequest.id.label("request_id"), models.SeqRequest.name.label("request_name"),
            models.User.id.label("requestor_id"), models.User.email.label("requestor_email"),
        ])

    if include_index_kit:
        columns.extend([
            models.IndexKit.id.label("index_kit_id"), models.IndexKit.name.label("index_kit_name"),
        ])

    if include_visium:
        columns.extend([
            models.VisiumAnnotation.slide.label("slide"), models.VisiumAnnotation.area.label("area"),
            models.VisiumAnnotation.image.label("image")
        ])

    if include_sample:
        columns.extend([
            models.Sample.id.label("sample_id"), models.Sample.name.label("sample_name"),
            models.SampleLibraryLink.cmo_sequence.label("cmo_sequence"), models.SampleLibraryLink.cmo_pattern.label("cmo_pattern"), models.SampleLibraryLink.cmo_read.label("cmo_read"),
        ])

    query = sa.select(*columns).join(
        models.Pool,
        models.Pool.id == models.Library.pool_id,
    ).join(
        models.LanePoolLink,
        models.LanePoolLink.pool_id == models.Pool.id,
        isouter=True
    ).join(
        models.Lane,
        models.Lane.id == models.LanePoolLink.lane_id,
    )

    if include_sample:
        query = query.join(
            models.SampleLibraryLink,
            models.SampleLibraryLink.library_id == models.Library.id,
        ).join(
            models.Sample,
            models.Sample.id == models.SampleLibraryLink.sample_id,
        )

    if include_seq_request:
        query = query.join(
            models.SeqRequest,
            models.SeqRequest.id == models.Library.seq_request_id,
        ).join(
            models.User,
            models.User.id == models.SeqRequest.requestor_id,
        )

    if include_index_kit:
        query = query.join(
            models.IndexKit,
            models.IndexKit.id == models.Library.index_kit_id,
            isouter=True
        )
    
    if include_visium:
        query = query.join(
            models.VisiumAnnotation,
            models.VisiumAnnotation.id == models.Library.visium_annotation_id,
            isouter=True
        )

    query = query.join(
        models.ExperimentPoolLink,
        models.ExperimentPoolLink.pool_id == models.Pool.id,
    ).where(
        models.ExperimentPoolLink.experiment_id == experiment_id
    )
            
    query = query.order_by(models.Library.id)
    df = pd.read_sql(query, self._engine)

    df["library_type"] = df["library_type_id"].map(categories.LibraryType.get)
    df["refernece"] = df["reference_id"].map(categories.GenomeRef.get)
    
    df = df.dropna(axis="columns", how="all")
    if collapse_lanes:
        df = df.groupby(df.columns.difference(['lane']).tolist(), as_index=False).agg({'lane': list}).rename(columns={'lane': 'lanes'})
    
    return df


def get_experiment_pools_df(self, experiment_id: int) -> pd.DataFrame:
    query = sa.select(
        models.Pool.id, models.Pool.name,
        models.Pool.status_id, models.Pool.num_libraries,
        models.Pool.num_m_reads_requested, models.Pool.qubit_concentration,
        models.Pool.avg_fragment_size,
    ).join(
        models.ExperimentPoolLink,
        models.ExperimentPoolLink.pool_id == models.Pool.id,
    ).where(
        models.ExperimentPoolLink.experiment_id == experiment_id
    )

    df = pd.read_sql(query, self._engine)
    df["status"] = df["status_id"].map(categories.PoolStatus.get)

    return df


def get_experiment_lanes_df(self, experiment_id: int) -> pd.DataFrame:
    query = sa.select(
        models.Lane.id, models.Lane.number.label("lane"),
        models.Lane.phi_x, models.Lane.original_qubit_concentration, models.Lane.total_volume_ul,
        models.Lane.library_volume_ul, models.Lane.avg_fragment_size, models.Lane.sequencing_qubit_concentration,
        models.Lane.target_molarity
    ).where(
        models.Lane.experiment_id == experiment_id
    ).order_by(models.Lane.number)

    df = pd.read_sql(query, self._engine)

    return df


def get_experiment_laned_pools_df(self, experiment_id: int) -> pd.DataFrame:
    query = sa.select(
        models.Lane.id, models.Lane.number.label("lane"),
        models.Pool.id.label("pool_id"), models.Pool.name.label("pool_name"),
        models.Pool.num_m_reads_requested, models.Pool.qubit_concentration,
        models.Pool.avg_fragment_size,
    ).where(
        models.Lane.experiment_id == experiment_id
    ).join(
        models.LanePoolLink,
        models.LanePoolLink.lane_id == models.Lane.id
    ).join(
        models.Pool,
        models.Pool.id == models.LanePoolLink.pool_id
    )

    df = pd.read_sql(query, self._engine)

    return df


def get_pool_libraries_df(self, pool_id: int) -> pd.DataFrame:
    query = sa.select(
        models.Library.id.label("library_id"), models.Library.name.label("library_name"), models.Library.type_id.label("library_type_id"),
        models.Library.adapter, models.IndexKit.id.label("index_kit_id"), models.IndexKit.name.label("index_kit_name"),
        models.Library.index_1_sequence.label("index_1"), models.Library.index_2_sequence.label("index_2"),
        models.Library.index_3_sequence.label("index_3"), models.Library.index_4_sequence.label("index_4"),
        models.Pool.id.label("pool_id"), models.Pool.name.label("pool_name"),
        models.User.id.label("owner_id"), models.User.email.label("owner_email"),
    ).join(
        models.Pool,
        models.Pool.id == models.Library.pool_id
    ).join(
        models.IndexKit,
        models.IndexKit.id == models.Library.index_kit_id,
        isouter=True
    ).join(
        models.User,
        models.User.id == models.Library.owner_id,
    ).where(
        models.Library.pool_id == pool_id,
    ).distinct()

    query = query.order_by(models.Library.id)

    df = pd.read_sql(query, self._engine)
    df["library_type"] = df["library_type_id"].map(categories.LibraryType.get)

    df = df.dropna(axis="columns", how="all")
    df = df.sort_values(by=["library_name"])

    return df


def get_seq_requestor_df(self, seq_request: int) -> pd.DataFrame:
    query = sa.select(
        models.SeqRequest.name.label("seq_request_name"),
        models.User.id.label("user_id"), models.User.email.label("email"),
        models.User.first_name.label("first_name"), models.User.last_name.label("last_name"),
        models.User.role_id.label("role_id")
    ).join(
        models.User,
        models.User.id == models.SeqRequest.requestor_id,
    ).where(
        models.SeqRequest.id == seq_request
    )

    df = pd.read_sql(query, self._engine)
    df["role"] = df["role_id"].map(categories.UserRole.get)

    return df


def get_seq_request_share_emails_df(self, seq_request: int) -> pd.DataFrame:
    query = sa.select(
        models.SeqRequestDeliveryEmailLink.email.label("email"),
        models.SeqRequestDeliveryEmailLink.status_id.label("status_id"),
    ).where(
        models.SeqRequestDeliveryEmailLink.seq_request_id == seq_request
    )

    df = pd.read_sql(query, self._engine)
    df["status"] = df["status_id"].map(categories.DeliveryStatus.get)

    return df


def get_library_features_df(self, library_id: int) -> pd.DataFrame:
    query = sa.select(
        models.Feature.id.label("feature_id"), models.Feature.name.label("feature_name"), models.Feature.type_id.label("feature_type_id"),
        models.Feature.target_id.label("target_id"), models.Feature.target_name.label("target_name"),
        models.Feature.sequence.label("sequence"), models.Feature.pattern.label("pattern"), models.Feature.read.label("read"),
        models.FeatureKit.id.label("feature_kit_id"), models.FeatureKit.name.label("feature_kit_name"),
    ).join(
        models.FeatureKit,
        models.FeatureKit.id == models.Feature.feature_kit_id,
        isouter=True
    ).join(
        models.LibraryFeatureLink,
        models.LibraryFeatureLink.feature_id == models.Feature.id
    ).where(
        models.LibraryFeatureLink.library_id == library_id
    ).distinct()

    df = pd.read_sql(query, self._engine)
    df["feature_type"] = df["feature_type_id"].map(categories.FeatureType.get)

    return df


def get_library_cmos_df(self, library_id: int) -> pd.DataFrame:
    query = sa.select(
        models.Sample.id.label("sample_id"), models.Sample.name.label("sample_name"),
        models.SampleLibraryLink.cmo_sequence.label("cmo_sequence"), models.SampleLibraryLink.cmo_pattern.label("cmo_pattern"), models.SampleLibraryLink.cmo_read.label("cmo_read"),
    ).join(
        models.SampleLibraryLink,
        models.SampleLibraryLink.sample_id == models.Sample.id
    ).where(
        models.SampleLibraryLink.library_id == library_id
    )

    df = pd.read_sql(query, self._engine)

    return df


def get_seq_request_libraries_df(
    self, seq_request_id: int,
    include_sample: bool = False, include_index_kit: bool = False,
    include_visium: bool = False, include_seq_request: bool = False,
) -> pd.DataFrame:
    
    columns = [
        models.Library.id.label("library_id"), models.Library.name.label("library_name"), models.Library.type_id.label("library_type_id"),
        models.Library.genome_ref_id.label("reference_id"),
        models.Library.adapter, models.Library.index_1_sequence.label("index_1"), models.Library.index_2_sequence.label("index_2"),
        models.Library.index_3_sequence.label("index_3"), models.Library.index_4_sequence.label("index_4"),
        models.Pool.id.label("pool_id"), models.Pool.name.label("pool_name"), models.Lane.number.label("lane"),
    ]
    if include_seq_request:
        columns.extend([
            models.SeqRequest.id.label("request_id"), models.SeqRequest.name.label("request_name"),
            models.User.id.label("requestor_id"), models.User.email.label("requestor_email"),
        ])

    if include_index_kit:
        columns.extend([
            models.IndexKit.id.label("index_kit_id"), models.IndexKit.name.label("index_kit_name"),
        ])

    if include_visium:
        columns.extend([
            models.VisiumAnnotation.slide.label("slide"), models.VisiumAnnotation.area.label("area"),
            models.VisiumAnnotation.image.label("image")
        ])

    if include_sample:
        columns.extend([
            models.Sample.id.label("sample_id"), models.Sample.name.label("sample_name"),
            models.SampleLibraryLink.cmo_sequence.label("cmo_sequence"), models.SampleLibraryLink.cmo_pattern.label("cmo_pattern"), models.SampleLibraryLink.cmo_read.label("cmo_read"),
        ])
    
    query = sa.select(
        *columns
    ).join(
        models.SeqRequest,
        models.SeqRequest.id == models.Library.seq_request_id
    ).join(
        models.Pool,
        models.Pool.id == models.Library.pool_id
    ).join(
        models.IndexKit,
        models.IndexKit.id == models.Library.index_kit_id,
        isouter=True
    ).join(
        models.User,
        models.User.id == models.Library.owner_id,
    ).where(
        models.Library.seq_request_id == seq_request_id,
    ).distinct()

    query = query.order_by(models.Library.id)

    df = pd.read_sql(query, self._engine)
    df["library_type"] = df["library_type_id"].map(categories.LibraryType.get)
    df = df.sort_values(by=["pool_name", "owner_email", "library_name"])

    return df


def get_experiment_seq_qualities_df(self, experiment_id: int) -> pd.DataFrame:
    query = sa.select(
        models.Library.id.label("library_id"), models.Library.name.label("library_name"),
        models.SeqQuality.lane, models.SeqQuality.num_lane_reads, models.SeqQuality.num_library_reads,
        models.SeqQuality.mean_quality_pf_r1, models.SeqQuality.q30_perc_r1,
        models.SeqQuality.mean_quality_pf_r2, models.SeqQuality.q30_perc_r2,
        models.SeqQuality.mean_quality_pf_i1, models.SeqQuality.q30_perc_i1,
        models.SeqQuality.mean_quality_pf_i2, models.SeqQuality.q30_perc_i2,
    ).join(
        models.Library,
        models.Library.id == models.SeqQuality.library_id,
        isouter=True
    ).where(
        models.SeqQuality.experiment_id == experiment_id
    )

    query = query.order_by(models.SeqQuality.lane, models.Library.id)
    df = pd.read_sql(query, self._engine)

    df.loc[df["library_name"].isna(), "library_id"] = -1
    df.loc[df["library_name"].isna(), "library_name"] = "Undetermined"
    df["library_id"] = df["library_id"].astype(int)

    return df