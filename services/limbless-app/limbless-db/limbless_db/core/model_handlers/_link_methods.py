import math
from typing import Optional

from ...categories import PoolStatus
from ... import models, PAGE_LIMIT
from .. import exceptions


def link_sample_library(
    self, sample_id: int, library_id: int,
    cmo_id: Optional[int] = None,
    commit: bool = True
) -> models.SampleLibraryLink:
    
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (sample := self._session.get(models.Sample, sample_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Sample with id {sample_id} does not exist")
    
    if (library := self._session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")
    
    if cmo_id is not None:
        if (_ := self._session.get(models.CMO, cmo_id)) is None:
            raise exceptions.ElementDoesNotExist(f"CMO with id {cmo_id} does not exist")
        
    if self._session.query(models.SampleLibraryLink).where(
        models.SampleLibraryLink.sample_id == sample_id,
        models.SampleLibraryLink.library_id == library_id,
    ).first():
        raise exceptions.LinkAlreadyExists(f"Sample with id {sample_id} and Library with id {library_id} are already linked")
    
    sample_library_link = models.SampleLibraryLink(
        sample_id=sample_id, library_id=library_id, cmo_id=cmo_id,
    )

    self._session.add(sample_library_link)
    sample.num_libraries += 1
    library.num_samples += 1

    if commit:
        self._session.commit()
        self._session.refresh(sample_library_link)

    if not persist_session:
        self.close_session()

    return sample_library_link


def get_sample_library_links(
    self,
    sample_id: Optional[int] = None,
    library_id: Optional[int] = None,
    seq_request_id: Optional[int] = None,
    limit: Optional[int] = PAGE_LIMIT,
    offset: Optional[int] = None,
) -> tuple[Optional[models.SampleLibraryLink], int]:
    
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.SampleLibraryLink)
    if sample_id is not None:
        query = query.where(models.SampleLibraryLink.sample_id == sample_id)

    if library_id is not None:
        query = query.where(models.SampleLibraryLink.library_id == library_id)

    if seq_request_id is not None:
        query = query.join(
            models.Library,
            models.Library.id == models.SampleLibraryLink.library_id,
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
    self, sample_id: int, seq_request_id: int
) -> bool:
    
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.Sample)

    query = query.join(
        models.SampleLibraryLink,
        models.SampleLibraryLink.sample_id == sample_id,
    ).join(
        models.Library,
        models.Library.id == models.SampleLibraryLink.library_id,
    ).where(
        models.Library.seq_request_id == seq_request_id,
    )

    res = query.first() is not None

    if not persist_session:
        self.close_session()

    return res


def link_feature_library(
    self, feature_id: int, library_id: int,
    commit: bool = True
) -> models.LibraryFeatureLink:
    
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (_ := self._session.get(models.Feature, feature_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Feature with id {feature_id} does not exist")
    
    if (library := self._session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")
    
    if self._session.query(models.LibraryFeatureLink).where(
        models.LibraryFeatureLink.feature_id == feature_id,
        models.LibraryFeatureLink.library_id == library_id,
    ).first():
        raise exceptions.LinkAlreadyExists(f"Feature with id {feature_id} and Library with id {library_id} are already linked")
    
    feature_library_link = models.LibraryFeatureLink(
        feature_id=feature_id, library_id=library_id,
    )

    self._session.add(feature_library_link)
    library.num_features += 1
    self._session.add(library)

    if commit:
        self._session.commit()
        self._session.refresh(feature_library_link)

    if not persist_session:
        self.close_session()

    return feature_library_link


def unlink_feature_library(
    self, feature_id: int, library_id: int,
    commit: bool = True
):
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (_ := self._session.get(models.Feature, feature_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Feature with id {feature_id} does not exist")
    
    if (library := self._session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")
    
    if (link := self._session.query(models.LibraryFeatureLink).where(
        models.LibraryFeatureLink.feature_id == feature_id,
        models.LibraryFeatureLink.library_id == library_id,
    ).first()) is None:
        raise exceptions.LinkDoesNotExist(f"Feature with id {feature_id} and Library with id {library_id} are not linked")
    
    self._session.delete(link)
    library.num_features -= 1
    self._session.add(library)

    if commit:
        self._session.commit()

    if not persist_session:
        self.close_session()


def link_pool_lane(
    self, lane_id: int, pool_id: int,
) -> models.LanePoolLink:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (_ := self._session.get(models.Lane, lane_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Lane with id {lane_id} does not exist")
    if (pool := self._session.get(models.Pool, pool_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Pool with id {pool_id} does not exist")
    
    if self._session.query(models.LanePoolLink).where(
        models.LanePoolLink.pool_id == pool_id,
        models.LanePoolLink.lane_id == lane_id,
    ).first():
        raise exceptions.LinkAlreadyExists(f"Lane with id '{lane_id}' and Pool with id '{pool_id}' are already linked.")

    link = models.LanePoolLink(
        lane_id=lane_id, pool_id=pool_id,
    )
    pool.status_id = PoolStatus.LANED.id
    self._session.add(link)
    self._session.commit()
    self._session.refresh(link)

    if not persist_session:
        self.close_session()

    return link


def unlink_pool_lane(self, lane_id, pool_id: int):
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (_ := self._session.get(models.Lane, lane_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Lane with id {lane_id} does not exist")
    if (_ := self._session.get(models.Pool, pool_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Pool with id {pool_id} does not exist")
    
    if (link := self._session.query(models.LanePoolLink).where(
        models.LanePoolLink.pool_id == pool_id,
        models.LanePoolLink.lane_id == lane_id,
    ).first()) is None:
        raise exceptions.LinkDoesNotExist(f"Lane with id '{lane_id}' and Pool with id '{pool_id}' are not linked.")
    
    self._session.delete(link)
    self._session.commit()

    if not persist_session:
        self.close_session()


def link_pool_experiment(self, experiment_id: int, pool_id: int):
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (_ := self._session.get(models.Experiment, experiment_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Experiment with id {experiment_id} does not exist")
    if (pool := self._session.get(models.Pool, pool_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Pool with id {pool_id} does not exist")

    if pool.experiment_id is not None:
        raise exceptions.LinkAlreadyExists(f"Pool with id {pool_id} is already linked to an experiment")
    
    pool = self._session.get(models.Pool, pool_id)
    pool.experiment_id = experiment_id
    pool.status_id = PoolStatus.ASSIGNED.id
    self._session.add(pool)
    self._session.commit()
    self._session.refresh(pool)

    if not persist_session:
        self.close_session()


def unlink_pool_experiment(self, experiment_id: int, pool_id: int):
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (_ := self._session.get(models.Experiment, experiment_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Experiment with id {experiment_id} does not exist")
    if (pool := self._session.get(models.Pool, pool_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Pool with id {pool_id} does not exist")

    if pool.experiment_id != experiment_id:
        raise exceptions.LinkDoesNotExist(f"Pool with id {pool_id} is not linked to experiment with id {experiment_id}")

    pool.experiment_id = None
    pool.status_id = PoolStatus.ACCEPTED.id
    self._session.add(pool)
    self._session.commit()

    if not persist_session:
        self.close_session()