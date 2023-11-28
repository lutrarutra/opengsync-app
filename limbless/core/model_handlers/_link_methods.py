from typing import Optional, Union

from sqlalchemy.orm import selectinload
from sqlmodel import and_

from ... import models, logger, categories
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


def get_project_data(
    self, project_id: int,
    unraveled: bool = False
) -> Union[list[models.Sample], list[tuple[models.Sample, models.Library]]]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if self._session.get(models.Project, project_id) is None:
        raise exceptions.ElementDoesNotExist(f"Project with id {project_id} does not exist")

    if not unraveled:
        project_data = self._session.query(models.Sample).where(
            models.Sample.project_id == project_id
        ).options(selectinload(models.Sample.libraries)).all()
    else:
        project_data = self._session.query(models.Sample, models.Library).join(
            models.LibrarySampleLink, models.Sample.id == models.LibrarySampleLink.sample_id
        ).join(
            models.Library, models.LibrarySampleLink.library_id == models.Library.id
        ).where(
            models.Sample.project_id == project_id
        ).all()

    if not persist_session:
        self.close_session()
    return project_data


def get_lanes_in_experiment(
    self, experiment_id: int
) -> dict[int, list[int]]:
    
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (_ := self._session.get(models.Experiment, experiment_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Experiment with id {experiment_id} does not exist")
    
    data = self._session.query(
        models.ExperimentLibraryLink.library_id,
        models.ExperimentLibraryLink.lane
    ).where(
        models.ExperimentLibraryLink.experiment_id == experiment_id
    ).order_by(models.ExperimentLibraryLink.lane).all()

    lanes: dict[int, list[int]] = {}
    for library_id, lane in data:
        if library_id not in lanes:
            lanes[library_id] = []
        lanes[library_id].append(lane)
    
    if not persist_session:
        self.close_session()

    return lanes


def is_sample_in_library(
    self, sample_id: int, library_id: int
) -> bool:
    
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.query(models.LibrarySampleLink).where(
        models.LibrarySampleLink.library_id == library_id,
        models.LibrarySampleLink.sample_id == sample_id
    ).first()

    logger.debug(res)

    if not persist_session:
        self.close_session()

    return res is not None
    

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
    if (sample := self._session.get(models.Library, library_id)) is None:
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


def link_library_barcode(
    self,
    library_id: int, barcode_id: int,
    barcode_type: categories.BarcodeType,
    commit: bool = True
) -> models.LibraryBarcodeLink:
    
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (library := self._session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")
    
    if (barcode := self._session.get(models.Barcode, barcode_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Barcode with id {barcode_id} does not exist")
    
    if self._session.query(models.LibraryBarcodeLink).where(
        models.LibraryBarcodeLink.library_id == library_id,
        models.LibraryBarcodeLink.barcode_id == barcode_id,
    ).first():
        raise exceptions.LinkAlreadyExists(f"Library with id {library_id} and barcode with id {barcode_id} are already linked for barcode type {barcode_type.value.name}")

    library_barcode_link = models.LibraryBarcodeLink(
        library_id=library_id, barcode_id=barcode_id,
    )
    self._session.add(library_barcode_link)

    if commit:
        self._session.commit()
        self._session.refresh(library_barcode_link)

    if not persist_session:
        self.close_session()

    return library_barcode_link


def link_library_seq_request(
    self, library_id: int, seq_request_id: int,
    commit: bool = True
) -> models.SeqRequestLibraryLink:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (_ := self._session.get(models.Library, library_id)) is None:
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

    if (_ := self._session.get(models.Library, library_id)) is None:
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

    if commit:
        self._session.commit()

    if not persist_session:
        self.close_session()


def link_experiment_library(
    self, experiment_id: int, library_id: int,
    lane: int, commit: bool = True
) -> models.ExperimentLibraryLink:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (experiment := self._session.get(models.Experiment, experiment_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Experiment with id {experiment_id} does not exist")
    if lane > experiment.num_lanes:
        raise exceptions.InvalidValue(f"Experiment with id {experiment_id} has only {experiment.num_lanes} lanes")
    if (library := self._session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")

    if self._session.query(models.ExperimentLibraryLink).where(
        models.ExperimentLibraryLink.experiment_id == experiment_id,
        models.ExperimentLibraryLink.library_id == library_id,
        models.ExperimentLibraryLink.lane == lane,
    ).first():
        raise exceptions.LinkAlreadyExists(f"Experiment with id {experiment_id} and Library with id {library_id} are already linked")

    experiment_library_link = models.ExperimentLibraryLink(
        experiment_id=experiment_id, library_id=library_id, lane=lane,
    )
    self._session.add(experiment_library_link)
    experiment.num_libraries += 1
    library.num_experiments += 1

    if commit:
        self._session.commit()
        self._session.refresh(experiment_library_link)

    if not persist_session:
        self.close_session()

    return experiment_library_link


def unlink_experiment_library(
    self, experiment_id: int, library_id: int, lane: int,
    commit: bool = True
):
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (experiment := self._session.get(models.Experiment, experiment_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Experiment with id {experiment_id} does not exist")
    if (library := self._session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")

    if (link := self._session.query(models.ExperimentLibraryLink).where(
        models.ExperimentLibraryLink.experiment_id == experiment_id,
        models.ExperimentLibraryLink.library_id == library_id,
        models.ExperimentLibraryLink.lane == lane,
    ).first()) is None:
        raise exceptions.ElementDoesNotExist(f"Experiment with id {experiment_id} and Library with id {library_id} are not linked")

    self._session.delete(link)
    experiment.num_libraries -= 1
    library.num_experiments -= 1
    if commit:
        self._session.commit()

    if not persist_session:
        self.close_session()
