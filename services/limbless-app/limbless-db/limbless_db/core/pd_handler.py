import pandas as pd

from .. import models
from . import exceptions, categories


def get_experiment_libraries_df(
    self, experiment_id: int
) -> pd.DataFrame:
        
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (_ := self._session.get(models.Experiment, experiment_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Experiment with id {experiment_id} does not exist")
    
    library_query = self._session.query(
        models.Library.id.label("library_id"), models.Library.name.label("library_name"), models.Library.type_id.label("library_type_id"),
        models.Library.adapter, models.IndexKit.id.label("index_kit_id"), models.IndexKit.name.label("index_kit_name"),
        models.Library.index_1_sequence.label("index_1"), models.Library.index_2_sequence.label("index_2"),
        models.Library.index_3_sequence.label("index_3"), models.Library.index_4_sequence.label("index_4"),
        models.Pool.id.label("pool_id"), models.Pool.name.label("pool_name"), models.ExperimentPoolLink.lane.label("lane"),
        models.SeqRequest.id.label("seq_request_id"), models.SeqRequest.name.label("request_name"),
        models.User.id.label("requestor_id"), models.User.email.label("requestor_email"),
        models.VisiumAnnotation.slide.label("slide"), models.VisiumAnnotation.area.label("area"), models.VisiumAnnotation.image.label("image")
    ).join(
        models.SeqRequest,
        models.SeqRequest.id == models.Library.seq_request_id,
    ).join(
        models.SeqRequestExperimentLink,
        models.SeqRequestExperimentLink.seq_request_id == models.Library.seq_request_id,
    ).where(
        models.SeqRequestExperimentLink.experiment_id == experiment_id
    ).join(
        models.Pool,
        models.Pool.id == models.Library.pool_id,
    ).join(
        models.User,
        models.User.id == models.SeqRequest.requestor_id,
    ).join(
        models.ExperimentPoolLink,
        models.ExperimentPoolLink.pool_id == models.Pool.id,
    ).join(
        models.IndexKit,
        models.IndexKit.id == models.Library.index_kit_id,
        isouter=True
    ).join(
        models.VisiumAnnotation,
        models.VisiumAnnotation.id == models.Library.visium_annotation_id,
        isouter=True
    ).distinct()

    library_query = library_query.order_by(models.Library.id)

    df = pd.read_sql(library_query.statement, library_query.session.bind)
    df["library_type"] = df["library_type_id"].apply(lambda x: categories.LibraryType.get(x).value.name)
    
    if not persist_session:
        self.close_session()

    return df


def get_experiment_samples_df(
    self, experiment_id: int
) -> pd.DataFrame:
        
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (_ := self._session.get(models.Experiment, experiment_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Experiment with id {experiment_id} does not exist")
    
    query = self._session.query(
        models.Sample.id.label("sample_id"), models.Sample.name.label("sample_name"), models.Organism.scientific_name.label("organism"), models.Sample.organism_id.label("tax_id"),
        models.Library.id.label("library_id"), models.Library.name.label("library_name"), models.Library.type_id.label("library_type_id"),
        models.Library.adapter, models.IndexKit.id.label("index_kit_id"), models.IndexKit.name.label("index_kit_name"),
        models.Library.index_1_sequence.label("index_1"), models.Library.index_2_sequence.label("index_2"),
        models.Library.index_3_sequence.label("index_3"), models.Library.index_4_sequence.label("index_4"),
        models.Pool.id.label("pool_id"), models.Pool.name.label("pool_name"), models.ExperimentPoolLink.lane.label("lane"),
        models.SeqRequest.id.label("seq_request_id"), models.SeqRequest.name.label("request_name"),
        models.User.id.label("requestor_id"), models.User.email.label("requestor_email"),
        models.CMO.sequence.label("cmo_sequence"), models.CMO.pattern.label("cmo_pattern"), models.CMO.read.label("cmo_read"),
        models.VisiumAnnotation.slide.label("slide"), models.VisiumAnnotation.area.label("area"), models.VisiumAnnotation.image.label("image")
    ).join(
        models.SampleLibraryLink,
        models.SampleLibraryLink.library_id == models.Library.id
    ).join(
        models.Sample,
        models.Sample.id == models.SampleLibraryLink.sample_id
    ).join(
        models.Organism,
        models.Organism.tax_id == models.Sample.organism_id
    ).join(
        models.CMO,
        models.CMO.id == models.SampleLibraryLink.cmo_id,
        isouter=True
    ).join(
        models.SeqRequest,
        models.SeqRequest.id == models.Library.seq_request_id,
    ).join(
        models.SeqRequestExperimentLink,
        models.SeqRequestExperimentLink.seq_request_id == models.Library.seq_request_id,
    ).where(
        models.SeqRequestExperimentLink.experiment_id == experiment_id
    ).join(
        models.Pool,
        models.Pool.id == models.Library.pool_id,
    ).join(
        models.User,
        models.User.id == models.SeqRequest.requestor_id,
    ).join(
        models.ExperimentPoolLink,
        models.ExperimentPoolLink.pool_id == models.Pool.id,
    ).join(
        models.IndexKit,
        models.IndexKit.id == models.Library.index_kit_id,
        isouter=True
    ).join(
        models.VisiumAnnotation,
        models.VisiumAnnotation.id == models.Library.visium_annotation_id,
        isouter=True
    ).distinct()

    query = query.order_by(models.Library.id)

    df = pd.read_sql(query.statement, query.session.bind)
    df["library_type"] = df["library_type_id"].apply(lambda x: categories.LibraryType.get(x).value.name)
    
    if not persist_session:
        self.close_session()

    return df