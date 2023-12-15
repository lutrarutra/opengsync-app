import math
from typing import Optional

from sqlmodel import and_

from ... import models, logger
from .. import exceptions


def get_sample_libraries(self, sample_id: int) -> list[models.Library]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if self._session.get(models.Sample, sample_id) is None:
        raise exceptions.ElementDoesNotExist(f"Sample with id {sample_id} does not exist")

    sample_libraries = self._session.query(models.Sample).join(
        models.Library,
        models.Library.sample_id == models.Sample.id
    ).all()

    if not persist_session:
        self.close_session()

    return sample_libraries


def get_lanes_in_experiment(
    self, experiment_id: int
) -> dict[int, list[int]]:
    
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (_ := self._session.get(models.Experiment, experiment_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Experiment with id {experiment_id} does not exist")
    
    data = self._session.query(
        models.ExperimentPoolLink.pool_id,
        models.ExperimentPoolLink.lane
    ).where(
        models.ExperimentPoolLink.experiment_id == experiment_id
    ).order_by(models.ExperimentPoolLink.lane).all()

    lanes: dict[int, list[int]] = {}
    for pool_id, lane in data:
        if pool_id not in lanes:
            lanes[pool_id] = []
        lanes[pool_id].append(lane)
    
    if not persist_session:
        self.close_session()

    return lanes


def get_available_pools_for_experiment(
    self, experiment_id: int
) -> list[models.Pool]:
    
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (_ := self._session.get(models.Experiment, experiment_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Experiment with id {experiment_id} does not exist")

    query = self._session.query(models.Pool).join(
        models.LibraryPoolLink,
        models.LibraryPoolLink.pool_id == models.Pool.id,
    ).join(
        models.Library,
        models.Library.id == models.LibraryPoolLink.library_id,
    ).join(
        models.SeqRequestLibraryLink,
        models.SeqRequestLibraryLink.library_id == models.Library.id,
    ).join(
        models.SeqRequestExperimentLink,
        models.SeqRequestExperimentLink.seq_request_id == models.SeqRequestLibraryLink.seq_request_id,
    ).where(
        models.SeqRequestExperimentLink.experiment_id == experiment_id,
    ).distinct()

    pools = query.all()

    if not persist_session:
        self.close_session()
    
    return pools


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
    

def link_library_pool(
    self,
    pool_id: int, library_id: int,
    commit: bool = True
) -> models.LibraryPoolLink:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (pool := self._session.get(models.Pool, pool_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Pool with id {pool_id} does not exist")
    if (library := self._session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")
    
    if self._session.query(models.LibraryPoolLink).where(
        and_(
            models.LibraryPoolLink.pool_id == pool_id,
            models.LibraryPoolLink.library_id == library_id,
        )
    ).first():
        raise exceptions.LinkAlreadyExists(f"Library with id {library_id} and pool with id {pool_id} are already linked")

    library_pool_link = models.LibraryPoolLink(
        pool_id=pool_id, library_id=library_id,
    )
    self._session.add(library_pool_link)
    library.num_pools += 1
    pool.num_libraries += 1

    if commit:
        self._session.commit()
        self._session.refresh(library_pool_link)

    if not persist_session:
        self.close_session()

    return library_pool_link


def get_sample_library_links(
    self,
    sample_id: Optional[int] = None,
    library_id: Optional[int] = None,
    limit: Optional[int] = None,
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
        models.Library,
        models.Library.sample_id == models.Sample.id,
    ).join(
        models.SeqRequestLibraryLink,
        models.SeqRequestLibraryLink.library_id == models.Library.id,
    ).distinct().where(
        and_(
            models.Sample.id == sample_id,
            models.SeqRequestLibraryLink.seq_request_id == seq_request_id,
        )
    )

    res = query.first() is not None

    logger.debug(query.first())

    if not persist_session:
        self.close_session()

    return res


def link_library_seq_request(
    self, library_id: int, seq_request_id: int,
    commit: bool = True
) -> models.SeqRequestLibraryLink:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (library := self._session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")
    if (seq_request := self._session.get(models.SeqRequest, seq_request_id)) is None:
        raise exceptions.ElementDoesNotExist(f"SeqRequest with id {seq_request_id} does not exist")

    if self._session.query(models.SeqRequestLibraryLink).where(
        models.SeqRequestLibraryLink.library_id == library_id,
        models.SeqRequestLibraryLink.seq_request_id == seq_request_id,
    ).first():
        raise exceptions.LinkAlreadyExists(f"Library with id {library_id} and SeqRequest with id {seq_request_id} are already linked")

    link = models.SeqRequestLibraryLink(
        library_id=library_id, seq_request_id=seq_request_id,
    )
    self._session.add(link)
    seq_request.num_libraries += 1
    library.num_seq_requests += 1
    self._session.add(seq_request)
    self._session.add(library)

    if commit:
        self._session.commit()
        self._session.refresh(link)

    if not persist_session:
        self.close_session()

    return link


def unlink_library_seq_request(
    self, library_id: int, seq_request_id: int,
    commit: bool = True
) -> None:
    
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (library := self._session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")
    if (seq_request := self._session.get(models.SeqRequest, seq_request_id)) is None:
        raise exceptions.ElementDoesNotExist(f"SeqRequest with id {seq_request_id} does not exist")
    
    if (links := self._session.query(models.SeqRequestLibraryLink).where(
        models.SeqRequestLibraryLink.library_id == library_id,
        models.SeqRequestLibraryLink.seq_request_id == seq_request_id,
    ).all()) is None:
        raise exceptions.LinkDoesNotExist(f"Library with id {library_id} and SeqRequest with id {seq_request_id} are not linked")
    
    for link in links:
        self._session.delete(link)

    seq_request.num_libraries -= 1
    library.num_seq_requests -= 1
    self._session.add(seq_request)
    self._session.add(library)

    if commit:
        self._session.commit()

    if not persist_session:
        self.close_session()


def link_experiment_pool(
    self, experiment_id: int, pool_id: int,
    lane: int, commit: bool = True
) -> models.ExperimentPoolLink:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (experiment := self._session.get(models.Experiment, experiment_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Experiment with id {experiment_id} does not exist")
    if lane > experiment.num_lanes:
        raise exceptions.InvalidValue(f"Experiment with id {experiment_id} has only {experiment.num_lanes} lanes")
    if (pool := self._session.get(models.Pool, pool_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Pool with id {pool_id} does not exist")

    if self._session.query(models.ExperimentPoolLink).where(
        models.ExperimentPoolLink.experiment_id == experiment_id,
        models.ExperimentPoolLink.pool_id == pool_id,
        models.ExperimentPoolLink.lane == lane,
    ).first():
        raise exceptions.LinkAlreadyExists(f"Experiment with id {experiment_id} and Pool with id {pool_id} are already linked.")

    experiment_library_link = models.ExperimentPoolLink(
        experiment_id=experiment_id, pool_id=pool_id, lane=lane,
    )
    self._session.add(experiment_library_link)
    experiment.num_pools += 1

    if commit:
        self._session.commit()
        self._session.refresh(experiment_library_link)

    if not persist_session:
        self.close_session()

    return experiment_library_link


def link_experiment_seq_request(
    self, experiment_id: int, seq_request_id: int,
    commit: bool = True
) -> models.SeqRequestExperimentLink:
    
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (experiment := self._session.get(models.Experiment, experiment_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Experiment with id {experiment_id} does not exist")
    if (seq_request := self._session.get(models.SeqRequest, seq_request_id)) is None:
        raise exceptions.ElementDoesNotExist(f"SeqRequest with id {seq_request_id} does not exist")

    if self._session.query(models.SeqRequestExperimentLink).where(
        models.SeqRequestExperimentLink.experiment_id == experiment_id,
        models.SeqRequestExperimentLink.seq_request_id == seq_request_id,
    ).first():
        raise exceptions.LinkAlreadyExists(f"Experiment with id {experiment_id} and SeqRequest with id {seq_request_id} are already linked")

    link = models.SeqRequestExperimentLink(
        experiment_id=experiment_id, seq_request_id=seq_request_id,
    )
    self._session.add(link)

    if commit:
        self._session.commit()
        self._session.refresh(link)

    if not persist_session:
        self.close_session()

    return link


def unlink_experiment_seq_request(
    self, experiment_id: int, seq_request_id: int,
    commit: bool = True
):
        
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (experiment := self._session.get(models.Experiment, experiment_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Experiment with id {experiment_id} does not exist")
    if (seq_request := self._session.get(models.SeqRequest, seq_request_id)) is None:
        raise exceptions.ElementDoesNotExist(f"SeqRequest with id {seq_request_id} does not exist")

    if (links := self._session.query(models.SeqRequestExperimentLink).where(
        models.SeqRequestExperimentLink.experiment_id == experiment_id,
        models.SeqRequestExperimentLink.seq_request_id == seq_request_id,
    ).all()) is None:
        raise exceptions.LinkDoesNotExist(f"Experiment with id {experiment_id} and SeqRequest with id {seq_request_id} are not linked")

    for link in links:
        self._session.delete(link)

    seq_request.num_experiments -= 1
    experiment.num_seq_requests -= 1
    self._session.add(seq_request)
    self._session.add(experiment)

    if commit:
        self._session.commit()

    if not persist_session:
        self.close_session()


def unlink_experiment_pool(
    self, experiment_id: int, pool_id: int, lane: int,
    commit: bool = True
):
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (experiment := self._session.get(models.Experiment, experiment_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Experiment with id {experiment_id} does not exist")
    if (library := self._session.get(models.Pool, pool_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Pool with id {pool_id} does not exist")

    if (link := self._session.query(models.ExperimentPoolLink).where(
        models.ExperimentPoolLink.experiment_id == experiment_id,
        models.ExperimentPoolLink.pool_id == pool_id,
        models.ExperimentPoolLink.lane == lane,
    ).first()) is None:
        raise exceptions.ElementDoesNotExist(f"Experiment with id {experiment_id} and Pool with id {pool_id} are not linked")

    self._session.delete(link)
    experiment.num_pools -= 1
    if commit:
        self._session.commit()

    if not persist_session:
        self.close_session()
