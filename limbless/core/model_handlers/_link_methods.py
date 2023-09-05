from typing import Optional, Union

from sqlalchemy.orm import selectinload
from sqlmodel import and_

from ... import models
from .. import exceptions
from ... import categories
from ...tools import SearchResult


def get_user_projects(self, user_id: int) -> list[models.Project]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if self._session.get(models.User, user_id) is None:
        raise exceptions.ElementDoesNotExist(f"User with id {user_id} does not exist")

    user_projects = self._session.query(models.Project).join(
        models.ProjectUserLink,
        models.ProjectUserLink.project_id == models.Project.id
    ).where(
        models.ProjectUserLink.user_id == user_id
    ).all()

    if not persist_session:
        self.close_session()
    return user_projects


def get_project_users(self, project_id: int) -> list[models.User]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if self._session.get(models.Project, project_id) is None:
        raise exceptions.ElementDoesNotExist(f"Project with id {project_id} does not exist")

    project_users = self._session.query(models.User).join(
        models.ProjectUserLink,
        models.ProjectUserLink.user_id == models.User.id
    ).where(
        models.ProjectUserLink.project_id == project_id
    ).all()

    if not persist_session:
        self.close_session()
    return project_users


def get_project_samples(self, project_id: int) -> list[models.Sample]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if self._session.get(models.Project, project_id) is None:
        raise exceptions.ElementDoesNotExist(f"Project with id {project_id} does not exist")

    project_samples = self._session.query(models.Sample).join(
        models.Organism, models.Sample.organism_id == models.Organism.tax_id
    ).options(
        selectinload(models.Sample.organism),
    ).where(
        models.Sample.project_id == project_id
    ).all()

    if not persist_session:
        self.close_session()
    return project_samples


def get_run_libraries(self, run_id: int) -> list[models.Library]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if self._session.get(models.Run, run_id) is None:
        raise exceptions.ElementDoesNotExist(f"Run with id {run_id} does not exist")

    run_libraries = self._session.query(models.Library).join(
        models.RunLibraryLink,
        models.RunLibraryLink.library_id == models.Library.id
    ).where(
        models.RunLibraryLink.run_id == run_id
    ).all()

    if not persist_session:
        self.close_session()
    return run_libraries


def get_library_runs(self, library_id: int) -> list[models.Run]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if self._session.get(models.Library, library_id) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")

    library_runs = self._session.query(models.Run).join(
        models.RunLibraryLink,
        models.RunLibraryLink.run_id == models.Run.id
    ).where(
        models.RunLibraryLink.library_id == library_id
    ).all()

    if not persist_session:
        self.close_session()
    return library_runs


def get_library_samples(self, library_id: int) -> list[models.Sample]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if self._session.get(models.Library, library_id) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")

    library_samples = self._session.query(models.Sample).join(
        models.LibrarySampleLink,
        models.LibrarySampleLink.sample_id == models.Sample.id
    ).join(
        models.Organism, models.Sample.organism_id == models.Organism.tax_id
    ).join(
        models.SeqIndex, models.LibrarySampleLink.seq_index_id == models.SeqIndex.id
    ).options(
        selectinload(models.Sample.organism),
        selectinload(models.Sample.indices)
    ).where(
        models.LibrarySampleLink.library_id == library_id
    ).all()

    if not persist_session:
        self.close_session()
    return library_samples


def get_sample_libraries(self, sample_id: int) -> list[models.Library]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if self._session.get(models.Sample, sample_id) is None:
        raise exceptions.ElementDoesNotExist(f"Sample with id {sample_id} does not exist")

    sample_libraries = self._session.query(models.Library).join(
        models.LibrarySampleLink,
        models.LibrarySampleLink.library_id == models.Library.id
    ).where(
        models.LibrarySampleLink.sample_id == sample_id
    ).all()

    if not persist_session:
        self.close_session()
    return sample_libraries

# TODO: testing


def get_experiment_runs(self, experiment_id: int) -> list[models.Run]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if self._session.get(models.Experiment, experiment_id) is None:
        raise exceptions.ElementDoesNotExist(f"Experiment with id {experiment_id} does not exist")

    experiment_runs = self._session.query(models.Run).where(
        models.Run.experiment_id == experiment_id
    ).all()

    if not persist_session:
        self.close_session()
    return experiment_runs

# TODO: testing


def get_experiment_data(
    self, experiment_id: int,
    unraveled: bool = False
) -> Union[list[models.Run], list[tuple[models.Run, models.Library, models.Sample]]]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if self._session.get(models.Experiment, experiment_id) is None:
        raise exceptions.ElementDoesNotExist(f"Experiment with id {experiment_id} does not exist")

    if not unraveled:
        experiment_data = self._session.query(models.Run).join(
            models.RunLibraryLink, models.Run.id == models.RunLibraryLink.run_id
        ).join(
            models.Library, models.RunLibraryLink.library_id == models.Library.id
        ).join(
            models.Experiment, models.Run.experiment_id == models.Experiment.id
        ).filter(
            models.Experiment.id == experiment_id
        ).options(
            selectinload(models.Run.libraries).selectinload(models.Library.samples)
        ).all()
    else:
        experiment_data = self._session.query(
            models.Run, models.Library, models.Sample
        ).join(
            models.RunLibraryLink, models.Library.id == models.RunLibraryLink.library_id
        ).join(
            models.Run, models.RunLibraryLink.run_id == models.Run.id
        ).join(
            models.Experiment, models.Run.experiment_id == models.Experiment.id
        ).join(
            models.LibrarySampleLink, models.Library.id == models.LibrarySampleLink.library_id
        ).join(
            models.Sample, models.LibrarySampleLink.sample_id == models.Sample.id
        ).where(
            models.Experiment.id == experiment_id
        ).all()

    if not persist_session:
        self.close_session()
    return experiment_data

# TODO: testing


def get_run_data(
    self, run_id: int,
    unraveled: bool = False
) -> Union[list[models.Library], list[tuple[models.Library, models.Sample]]]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if self._session.get(models.Run, run_id) is None:
        raise exceptions.ElementDoesNotExist(f"Run with id {run_id} does not exist")

    if not unraveled:
        run_data = self._session.query(models.Library).join(
            models.RunLibraryLink, models.Library.id == models.RunLibraryLink.library_id
        ).filter(
            models.RunLibraryLink.run_id == run_id
        ).options(selectinload(models.Library.samples)).all()
    else:
        run_data = self._session.query(models.Library, models.Sample).join(
            models.LibrarySampleLink, models.Sample.id == models.LibrarySampleLink.sample_id
        ).join(
            models.Library, models.LibrarySampleLink.library_id == models.Library.id
        ).join(
            models.RunLibraryLink, models.Library.id == models.RunLibraryLink.library_id
        ).filter(
            models.RunLibraryLink.run_id == run_id
        ).all()

    if not persist_session:
        self.close_session()
    return run_data


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


def link_project_user(
    self, project_id: int, user_id: int,
    role: categories.ProjectRole,
    commit: bool = True
) -> models.ProjectUserLink:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    user = self._session.get(models.User, user_id)
    project = self._session.get(models.Project, project_id)

    if not user:
        raise exceptions.ElementDoesNotExist(f"User with id {user_id} does not exist")
    if not project:
        raise exceptions.ElementDoesNotExist(f"Project with id {project_id} does not exist")

    if self._session.query(models.ProjectUserLink).where(
        models.ProjectUserLink.project_id == project_id,
        models.ProjectUserLink.user_id == user_id
    ).first():
        raise exceptions.LinkAlreadyExists(f"User with id {user_id} and project with id {project_id} are already linked")

    project_user_link = models.ProjectUserLink(
        project_id=project_id, user_id=user_id,
        role=role.id
    )
    self._session.add(project_user_link)

    if commit:
        self._session.commit()
        self._session.refresh(project_user_link)

    if not persist_session:
        self.close_session()
    return project_user_link


def unlink_project_user(
    self, project_id: int, user_id: int,
    commit: bool = True
) -> None:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    user = self._session.get(models.User, user_id)
    project = self._session.get(models.Project, project_id)

    if not user:
        raise exceptions.ElementDoesNotExist(f"User with id {user_id} does not exist")
    if not project:
        raise exceptions.ElementDoesNotExist(f"Project with id {project_id} does not exist")

    if not self._session.query(models.ProjectUserLink).where(
        models.ProjectUserLink.project_id == project_id,
        models.ProjectUserLink.user_id == user_id
    ).first():
        raise exceptions.LinkDoesNotExist(f"User with id {user_id} and project with id {project_id} are already linked")

    project.users.remove(user)

    if commit:
        self._session.commit()

    if not persist_session:
        self.close_session()


def link_run_library(
    self, run_id: int, library_id: int,
    commit: bool = True
) -> models.RunLibraryLink:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    run = self._session.get(models.Run, run_id)
    library = self._session.get(models.Library, library_id)

    if not run:
        raise exceptions.ElementDoesNotExist(f"Run with id {run_id} does not exist")
    if not library:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")

    if self._session.query(models.RunLibraryLink).where(
        models.RunLibraryLink.run_id == run_id,
        models.RunLibraryLink.library_id == library_id
    ).first():
        raise exceptions.LinkAlreadyExists(f"Run with id {run_id} and library with id {library_id} are already linked")

    run_library_link = models.RunLibraryLink(
        run_id=run_id, library_id=library_id
    )
    self._session.add(run_library_link)

    if commit:
        self._session.commit()
        self._session.refresh(run_library_link)

    if not persist_session:
        self.close_session()
    return run_library_link


def unlink_run_library(
    self, run_id: int, library_id: int,
    commit: bool = True
) -> None:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    run = self._session.get(models.Run, run_id)
    library = self._session.get(models.Library, library_id)

    if not run:
        raise exceptions.ElementDoesNotExist(f"Run with id {run_id} does not exist")
    if not library:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")

    if not self._session.query(models.RunLibraryLink).where(
        models.RunLibraryLink.run_id == run_id,
        models.RunLibraryLink.library_id == library_id
    ).first():
        raise exceptions.LinkDoesNotExist(f"Run with id {run_id} and library with id {library_id} are already linked")

    run.libraries.remove(library)

    if commit:
        self._session.commit()

    if not persist_session:
        self.close_session()


def link_library_sample(
    self,
    library_id: int,
    sample_id: int,
    seq_index_id: int,
    commit: bool = True
) -> models.LibrarySampleLink:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (library := self._session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")
    if (sample := self._session.get(models.Sample, sample_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Sample with id {sample_id} does not exist")
    if (seq_index := self._session.get(models.SeqIndex, seq_index_id)) is None:
        raise exceptions.ElementDoesNotExist(f"SeqIndex with id {seq_index_id} does not exist")

    if self._session.query(models.LibrarySampleLink).where(
        models.LibrarySampleLink.library_id == library_id,
        models.LibrarySampleLink.sample_id == sample_id,
        models.LibrarySampleLink.seq_index_id == seq_index_id,
    ).first():
        raise exceptions.LinkAlreadyExists(f"Library with id {library_id} and sample with id {sample_id} are already linked")

    library_sample_link = models.LibrarySampleLink(
        library_id=library_id, sample_id=sample_id,
        seq_index_id=seq_index_id
    )
    self._session.add(library_sample_link)

    if commit:
        self._session.commit()
        self._session.refresh(library_sample_link)

    if not persist_session:
        self.close_session()
    return library_sample_link


def unlink_library_sample(
    self, library_id: int, sample_id: int,
    commit: bool = True
) -> None:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    library = self._session.get(models.Library, library_id)
    sample = self._session.get(models.Sample, sample_id)

    if not library:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")
    if not sample:
        raise exceptions.ElementDoesNotExist(f"Sample with id {sample_id} does not exist")

    if not self._session.query(models.LibrarySampleLink).where(
        models.LibrarySampleLink.library_id == library_id,
        models.LibrarySampleLink.sample_id == sample_id
    ).first():
        raise exceptions.LinkDoesNotExist(f"Library with id {library_id} and sample with id {sample_id} are not linked")

    library.samples.remove(sample)

    if commit:
        self._session.commit()

    if not persist_session:
        self.close_session()


def get_user_samples(
    self, user_id: int,
    limit: Optional[int] = None,
) -> list[models.Sample]:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.query(models.Sample).join(
        models.Project,
        models.Sample.project_id == models.Project.id
    ).join(
        models.ProjectUserLink,
        and_(
            models.ProjectUserLink.project_id == models.Project.id,
            models.ProjectUserLink.user_id == user_id,
        )
    ).options(
        selectinload(models.Sample.project)
    ).where(
        models.User.id == user_id
    )

    if limit is not None:
        res = res.limit(limit)
    res = res.all()

    # res = [SearchResult(sample.id, sample.name, sample.project.name) for sample in res]

    if not persist_session:
        self.close_session()

    return res
