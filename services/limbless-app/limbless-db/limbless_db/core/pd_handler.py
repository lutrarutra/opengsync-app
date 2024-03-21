# pyright: reportMissingImports=false, reportUnusedVariable=false, reportUntypedBaseClass=error
import pandas as pd

from sqlalchemy.sql.operators import and_  # noqa: F401

from .. import models
from . import exceptions
from .. import categories


def get_experiment_libraries_df(
    self, experiment_id: int,
    include_sample: bool = False, include_index_kit: bool = False,
    include_visium: bool = False, include_seq_request: bool = False,
    include_reads_requested: bool = False
) -> pd.DataFrame:
        
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    a = 0

    if (_ := self._session.get(models.Experiment, experiment_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Experiment with id {experiment_id} does not exist")
    
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
            models.CMO.sequence.label("cmo_sequence"), models.CMO.pattern.label("cmo_pattern"), models.CMO.read.label("cmo_read"),
        ])

    if include_reads_requested:
        columns.append(
            models.Pool.num_m_reads_requested.label("pool_reads_requested"),
        )

    query = self._session.query(*columns).join(
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
            models.CMO,
            models.CMO.id == models.SampleLibraryLink.cmo_id,
            isouter=True
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
            
    library_query = query.order_by(models.Library.id)
    df = pd.read_sql(str(library_query.statement), self._url)
    df["library_type"] = df["library_type_id"].apply(lambda x: categories.LibraryType.get(x).abbreviation)
    df["refernece"] = df["reference_id"].apply(lambda x: categories.GenomeRef.get(x).assembly)

    df = df.dropna(axis="columns", how="all")
    
    if not persist_session:
        self.close_session()

    return df


def get_pool_libraries_df(self, pool_id: int) -> pd.DataFrame:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (_ := self._session.get(models.Pool, pool_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Pool with id {pool_id} does not exist")
    
    query = self._session.query(
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

    df = pd.read_sql(query.statement, query.session.bind)
    df["library_type"] = df["library_type_id"].apply(lambda x: categories.LibraryType.get(x).name)

    df = df.dropna(axis="columns", how="all")
    df = df.sort_values(by=["library_name"])
    
    if not persist_session:
        self.close_session()

    return df


def get_seq_requestor_df(self, seq_request: int) -> pd.DataFrame:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (_ := self._session.get(models.SeqRequest, seq_request)) is None:
        raise exceptions.ElementDoesNotExist(f"SeqRequest with id {seq_request} does not exist")
    
    query = self._session.query(
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

    df = pd.read_sql(query.statement, query.session.bind)
    df["role"] = df["role_id"].apply(lambda x: categories.UserRole.get(x).name)

    if not persist_session:
        self.close_session()

    return df


def get_seq_request_share_emails_df(self, seq_request: int) -> pd.DataFrame:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (_ := self._session.get(models.SeqRequest, seq_request)) is None:
        raise exceptions.ElementDoesNotExist(f"SeqRequest with id {seq_request} does not exist")
    
    query = self._session.query(
        models.SeqRequestShareEmailLink.email.label("email"), models.SeqRequestShareEmailLink.status_id.label("status_id"),
    ).where(
        models.SeqRequestShareEmailLink.seq_request_id == seq_request
    )

    df = pd.read_sql(query.statement, query.session.bind)
    df["status"] = df["status_id"].apply(lambda x: categories.DeliveryStatus.get(x).name)

    if not persist_session:
        self.close_session()

    return df


def get_library_features_df(self, library_id: int) -> pd.DataFrame:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (_ := self._session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")
    
    query = self._session.query(
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

    df = pd.read_sql(query.statement, query.session.bind)
    df["feature_type"] = df["feature_type_id"].apply(lambda x: categories.FeatureType.get(x).name)

    if not persist_session:
        self.close_session()

    return df


def get_library_cmos_df(self, library_id: int) -> pd.DataFrame:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (_ := self._session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")
    
    query = self._session.query(
        models.Sample.id.label("sample_id"), models.Sample.name.label("sample_name"), models.Sample.organism_id.label("tax_id"),
        models.CMO.id.label("cmo_id"), models.CMO.sequence.label("sequence"), models.CMO.pattern.label("pattern"), models.CMO.read.label("read"),
    ).join(
        models.SampleLibraryLink,
        models.SampleLibraryLink.sample_id == models.Sample.id
    ).where(
        models.SampleLibraryLink.library_id == library_id
    ).join(
        models.CMO,
        models.CMO.id == models.SampleLibraryLink.cmo_id
    ).distinct()

    df = pd.read_sql(query.statement, query.session.bind)

    if not persist_session:
        self.close_session()

    return df


def get_seq_request_libraries_df(self, seq_request: int) -> pd.DataFrame:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (_ := self._session.get(models.SeqRequest, seq_request)) is None:
        raise exceptions.ElementDoesNotExist(f"SeqRequest with id {seq_request} does not exist")
    
    query = self._session.query(
        models.Library.id.label("library_id"), models.Library.name.label("library_name"), models.Library.type_id.label("library_type_id"),
        models.Library.adapter, models.IndexKit.id.label("index_kit_id"), models.IndexKit.name.label("index_kit_name"),
        models.Library.index_1_sequence.label("index_1"), models.Library.index_2_sequence.label("index_2"),
        models.Library.index_3_sequence.label("index_3"), models.Library.index_4_sequence.label("index_4"),
        models.Pool.id.label("pool_id"), models.Pool.name.label("pool_name"),
        models.User.id.label("owner_id"), models.User.email.label("owner_email"),
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
        models.Library.seq_request_id == seq_request,
    ).distinct()

    query = query.order_by(models.Library.id)

    df = pd.read_sql(query.statement, query.session.bind)
    df["library_type"] = df["library_type_id"].apply(lambda x: categories.LibraryType.get(x).name)
    df = df.dropna(axis="columns", how="all")
    df = df.sort_values(by=["pool_name", "owner_email", "library_name"])
    
    if not persist_session:
        self.close_session()

    return df


def get_experiment_seq_qualities_df(self, experiment_id: int) -> pd.DataFrame:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (_ := self._session.get(models.Experiment, experiment_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Experiment with id {experiment_id} does not exist")
    
    query = self._session.query(
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
    df = pd.read_sql(query.statement, query.session.bind)

    df.loc[df["library_name"].isna(), "library_id"] = -1
    df.loc[df["library_name"].isna(), "library_name"] = "Undetermined"
    df["library_id"] = df["library_id"].astype(int)

    if not persist_session:
        self.close_session()

    return df