import math
from typing import Optional, TYPE_CHECKING

from sqlalchemy import and_

if TYPE_CHECKING:
    from ..DBHandler import DBHandler
from ... import models, PAGE_LIMIT
from .. import exceptions


def link_sample_library(
    self: "DBHandler", sample_id: int, library_id: int,
    cmo_sequence: Optional[str] = None,
    cmo_pattern: Optional[str] = None,
    cmo_read: Optional[str] = None,
    flex_barcode: Optional[str] = None,
    commit: bool = True
) -> models.links.SampleLibraryLink:
    
    if not (persist_session := self._session is not None):
        self.open_session()

    if (sample := self.session.get(models.Sample, sample_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Sample with id {sample_id} does not exist")
    
    if (library := self.session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")
        
    if self.session.query(models.links.SampleLibraryLink).where(
        models.links.SampleLibraryLink.sample_id == sample_id,
        models.links.SampleLibraryLink.library_id == library_id,
    ).first():
        raise exceptions.LinkAlreadyExists(f"Sample with id {sample_id} and Library with id {library_id} are already linked")
    
    sample_library_link = models.links.SampleLibraryLink(
        sample_id=sample_id, library_id=library_id,
        cmo_sequence=cmo_sequence,
        cmo_pattern=cmo_pattern,
        cmo_read=cmo_read,
        flex_barcode=flex_barcode,
    )

    self.session.add(sample_library_link)
    sample.num_libraries += 1
    library.num_samples += 1

    if commit:
        self.session.commit()
        self.session.refresh(sample_library_link)

    if not persist_session:
        self.close_session()

    return sample_library_link


def get_sample_library_links(
    self: "DBHandler",
    sample_id: Optional[int] = None,
    library_id: Optional[int] = None,
    seq_request_id: Optional[int] = None,
    limit: Optional[int] = PAGE_LIMIT,
    offset: Optional[int] = None,
) -> tuple[list[models.links.SampleLibraryLink], int]:
    
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.links.SampleLibraryLink)
    if sample_id is not None:
        query = query.where(models.links.SampleLibraryLink.sample_id == sample_id)

    if library_id is not None:
        query = query.where(models.links.SampleLibraryLink.library_id == library_id)

    if seq_request_id is not None:
        query = query.join(
            models.Library,
            models.Library.id == models.links.SampleLibraryLink.library_id,
        ).where(
            models.Library.seq_request_id == seq_request_id,
        )
    
    n_pages: int = math.ceil(query.count() / limit) if limit is not None else 1

    if limit is not None:
        query = query.limit(limit)
    if offset is not None:
        query = query.offset(offset)

    links = query.all()

    if not persist_session:
        self.close_session()

    return links, n_pages


def is_sample_in_seq_request(
    self: "DBHandler", sample_id: int, seq_request_id: int
) -> bool:
    
    if not (persist_session := self._session is not None):
        self.open_session()

    query = self.session.query(models.Sample)

    query = query.join(
        models.links.SampleLibraryLink,
        models.links.SampleLibraryLink.sample_id == sample_id,
    ).join(
        models.Library,
        models.Library.id == models.links.SampleLibraryLink.library_id,
    ).where(
        models.Library.seq_request_id == seq_request_id,
    )

    res = query.first() is not None

    if not persist_session:
        self.close_session()

    return res


def link_feature_library(self: "DBHandler", feature_id: int, library_id: int):
    if not (persist_session := self._session is not None):
        self.open_session()

    if (feature := self.session.get(models.Feature, feature_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Feature with id {feature_id} does not exist")
    
    if (library := self.session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")
    
    if self.session.query(models.links.LibraryFeatureLink).where(
        models.links.LibraryFeatureLink.feature_id == feature_id,
        models.links.LibraryFeatureLink.library_id == library_id,
    ).first():
        raise exceptions.LinkAlreadyExists(f"Feature with id {feature_id} and Library with id {library_id} are already linked")
    
    library.features.append(feature)
    library.num_features += 1
    self.session.add(library)
    self.session.commit()

    if not persist_session:
        self.close_session()


def unlink_feature_library(self: "DBHandler", feature_id: int, library_id: int):
    if not (persist_session := self._session is not None):
        self.open_session()

    if (feature := self.session.get(models.Feature, feature_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Feature with id {feature_id} does not exist")
    
    if (library := self.session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")
    
    if (_ := self.session.query(models.links.LibraryFeatureLink).where(
        models.links.LibraryFeatureLink.feature_id == feature_id,
        models.links.LibraryFeatureLink.library_id == library_id,
    ).first()) is None:
        raise exceptions.LinkDoesNotExist(f"Feature with id {feature_id} and Library with id {library_id} are not linked")
    
    library.features.remove(feature)
    library.num_features -= 1
    self.session.add(library)
    self.session.commit()

    if not persist_session:
        self.close_session()


def add_pool_to_lane(
    self: "DBHandler", experiment_id: int, pool_id: int, lane_num: int
) -> models.Lane:

    if not (persist_session := self._session is not None):
        self.open_session()

    if (lane := self.session.query(models.Lane).where(
        models.Lane.experiment_id == experiment_id,
        models.Lane.number == lane_num,
    ).first()) is None:
        raise exceptions.ElementDoesNotExist(f"Lane with number {lane_num} does not exist in experiment with id {experiment_id}")
    if (pool := self.session.get(models.Pool, pool_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Pool with id {pool_id} does not exist")
    
    if self.session.query(models.links.LanePoolLink).where(
        models.links.LanePoolLink.pool_id == pool_id,
        models.links.LanePoolLink.lane_id == lane.id,
    ).first():
        raise exceptions.LinkAlreadyExists(f"Lane with id '{lane.id}' and Pool with id '{pool_id}' are already linked.")
    
    lane.pools.append(pool)
    
    self.session.add(lane)
    self.session.commit()
    self.session.refresh(lane)

    if not persist_session:
        self.close_session()

    return lane


def remove_pool_from_lane(self: "DBHandler", experiment_id: int, pool_id: int, lane_num: int) -> models.Lane:
    if not (persist_session := self._session is not None):
        self.open_session()

    if (lane := self.session.query(models.Lane).where(
        models.Lane.experiment_id == experiment_id,
        models.Lane.number == lane_num,
    ).first()) is None:
        raise exceptions.ElementDoesNotExist(f"Lane with number {lane_num} does not exist in experiment with id {experiment_id}")
    if (pool := self.session.get(models.Pool, pool_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Pool with id {pool_id} does not exist")
    
    if self.session.query(models.links.LanePoolLink).where(
        models.links.LanePoolLink.pool_id == pool_id,
        models.links.LanePoolLink.lane_id == lane.id,
    ).first() is None:
        raise exceptions.LinkDoesNotExist(f"Lane with id '{lane.id}' and Pool with id '{pool_id}' are not linked.")
    
    lane.pools.remove(pool)
    self.session.add(lane)
    self.session.commit()
    self.session.refresh(lane)

    if not persist_session:
        self.close_session()

    return lane


def link_pool_experiment(self: "DBHandler", experiment_id: int, pool_id: int):
    if not (persist_session := self._session is not None):
        self.open_session()

    if (experiment := self.session.get(models.Experiment, experiment_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Experiment with id {experiment_id} does not exist")
    if (pool := self.session.get(models.Pool, pool_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Pool with id {pool_id} does not exist")
    if self.session.query(models.links.ExperimentPoolLink).where(
        and_(
            models.links.ExperimentPoolLink.experiment_id == experiment_id,
            models.links.ExperimentPoolLink.pool_id == pool_id
        )
    ).first() is not None:
        raise exceptions.LinkAlreadyExists(f"Pool with id {pool_id} is already linked to an experiment")

    experiment.pools.append(pool)

    if experiment.workflow.combined_lanes:
        for lane in experiment.lanes:
            self.add_pool_to_lane(experiment_id=experiment_id, pool_id=pool_id, lane_num=lane.number)

    self.session.add(experiment)
    self.session.commit()

    if not persist_session:
        self.close_session()


def unlink_pool_experiment(self: "DBHandler", experiment_id: int, pool_id: int):
    if not (persist_session := self._session is not None):
        self.open_session()

    if (experiment := self.session.get(models.Experiment, experiment_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Experiment with id {experiment_id} does not exist")

    if (pool := self.session.get(models.Pool, pool_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Pool with id {pool_id} does not exist")
    if self.session.query(models.links.ExperimentPoolLink).where(
        and_(
            models.links.ExperimentPoolLink.experiment_id == experiment_id,
            models.links.ExperimentPoolLink.pool_id == pool_id
        )
    ).first() is None:
        raise exceptions.LinkDoesNotExist(f"Pool with id {pool_id} is not linked to experiment with id {experiment_id}")
    
    for lane in experiment.lanes:
        if (link := self.session.query(models.links.LanePoolLink).where(
            models.links.LanePoolLink.pool_id == pool_id,
            models.links.LanePoolLink.lane_id == lane.id,
        ).first()) is not None:
            self.session.delete(link)
            self.session.commit()

    experiment.pools.remove(pool)
    self.session.add(experiment)
    self.session.commit()

    if not persist_session:
        self.close_session()