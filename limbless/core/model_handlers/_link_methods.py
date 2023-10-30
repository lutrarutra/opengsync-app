from typing import Optional, Union

from sqlalchemy.orm import selectinload
from sqlmodel import and_

from ... import models, logger, categories
from .. import exceptions


def get_sample_indices_from_library(
    self, sample_id: int, library_id: int
) -> list[models.SeqIndex]:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if self._session.get(models.Sample, sample_id) is None:
        raise exceptions.ElementDoesNotExist(f"Sample with id {sample_id} does not exist")
    
    if self._session.get(models.Library, library_id) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")
    
    res = self._session.query(models.SeqIndex).join(
        models.LibrarySampleLink,
        and_(
            models.LibrarySampleLink.library_id == library_id,
            models.LibrarySampleLink.sample_id == sample_id,
            models.LibrarySampleLink.seq_index_id == models.SeqIndex.id
        )
    ).all()

    if not persist_session:
        self.close_session()

    return res


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


def get_library_samples(self, library_id: int) -> list[models.Sample]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if self._session.get(models.Library, library_id) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")

    res = self._session.query(models.Sample, models.SeqIndex).join(
        models.LibrarySampleLink,
        and_(
            models.LibrarySampleLink.sample_id == models.Sample.id,
            models.LibrarySampleLink.library_id == library_id
        )
    ).join(
        models.SeqIndex,
        models.LibrarySampleLink.seq_index_id == models.SeqIndex.id
    ).where(
        models.LibrarySampleLink.library_id == library_id
    ).all()

    library_samples = {}
    for sample, seq_index in res:
        if sample.id not in library_samples:
            library_samples[sample.id] = sample
            library_samples[sample.id].indices = []

        library_samples[sample.id].indices.append(seq_index)

    library_samples = list(library_samples.values())

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

# def link_library_user(
#     self, library_id: int, user_id: int,
#     relation: categories.UserResourceRelation
# ) -> models.LibraryUserLink:
#     persist_session = self._session is not None
#     if not self._session:
#         self.open_session()

#     if (_ := self._session.get(models.User, user_id)) is None:
#         raise exceptions.ElementDoesNotExist(f"User with id {user_id} does not exist")
#     if (_ := self._session.get(models.Library, library_id)) is None:
#         raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")

#     if self._session.query(models.LibraryUserLink).where(
#         models.LibraryUserLink.library_id == library_id,
#         models.LibraryUserLink.user_id == user_id
#     ).first():
#         raise exceptions.LinkAlreadyExists(f"User with id {user_id} and library with id {library_id} are already linked")

#     library_user_link = models.LibraryUserLink(
#         library_id=library_id, user_id=user_id,
#         relation_id=relation.value.id
#     )
#     self._session.add(library_user_link)

#     self._session.commit()
#     self._session.refresh(library_user_link)

#     if not persist_session:
#         self.close_session()
#     return library_user_link


# def link_project_user(
#     self, project_id: int, user_id: int,
#     relation: categories.UserResourceRelation,
#     commit: bool = True
# ) -> models.ProjectUserLink:

#     persist_session = self._session is not None
#     if not self._session:
#         self.open_session()

#     if (_ := self._session.get(models.User, user_id)) is None:
#         raise exceptions.ElementDoesNotExist(f"User with id {user_id} does not exist")
#     if (_ := self._session.get(models.Project, project_id)) is None:
#         raise exceptions.ElementDoesNotExist(f"Project with id {project_id} does not exist")

#     if self._session.query(models.ProjectUserLink).where(
#         models.ProjectUserLink.project_id == project_id,
#         models.ProjectUserLink.user_id == user_id
#     ).first():
#         raise exceptions.LinkAlreadyExists(f"User with id {user_id} and project with id {project_id} are already linked")

#     project_user_link = models.ProjectUserLink(
#         project_id=project_id, user_id=user_id,
#         relation_id=relation.value.id
#     )
#     self._session.add(project_user_link)

#     if commit:
#         self._session.commit()
#         self._session.refresh(project_user_link)

#     if not persist_session:
#         self.close_session()
#     return project_user_link


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
    

def link_library_sample(
    self,
    library_id: int,
    sample_id: int,
    seq_index_id: Optional[int] = None,
    commit: bool = True
) -> models.LibrarySampleLink:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if seq_index_id is None:
        seq_index_id = 0

    if (_ := self._session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")
    if (_ := self._session.get(models.Sample, sample_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Sample with id {sample_id} does not exist")
    if (_ := self._session.get(models.SeqIndex, seq_index_id)) is None:
        raise exceptions.ElementDoesNotExist(f"SeqIndex with id {seq_index_id} does not exist")

    if self._session.query(models.LibrarySampleLink).where(
        and_(
            models.LibrarySampleLink.library_id == library_id,
            models.LibrarySampleLink.sample_id == sample_id,
            models.LibrarySampleLink.seq_index_id == seq_index_id,
        )
    ).first():
        raise exceptions.LinkAlreadyExists(f"Library with id {library_id} and sample with id {sample_id} are already linked")

    library_sample_link = models.LibrarySampleLink(
        library_id=library_id, sample_id=sample_id,
        seq_index_id=seq_index_id if seq_index_id is not None else 0
    )
    self._session.add(library_sample_link)

    if commit:
        self._session.commit()
        self._session.refresh(library_sample_link)

    if not persist_session:
        self.close_session()
    return library_sample_link


def link_index_kit_library_type(
    self, index_kit_id: int, library_type_id: int,
) -> models.IndexKitLibraryType:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (_ := self._session.get(models.IndexKit, index_kit_id)) is None:
        raise exceptions.ElementDoesNotExist(f"index_kit with id {index_kit_id} does not exist")

    if not categories.LibraryType.is_valid(library_type_id):
        raise exceptions.ElementDoesNotExist(f"LibraryType with id {library_type_id} is not valid")

    if self._session.query(models.IndexKitLibraryType).where(
        models.IndexKitLibraryType.index_kit_id == index_kit_id,
        models.IndexKitLibraryType.library_type_id == library_type_id,
    ).first():
        raise exceptions.LinkAlreadyExists(f"index_kit with id {index_kit_id} and LibraryType with id {library_type_id} are already linked")

    index_kit_library_type_link = models.IndexKitLibraryType(
        index_kit_id=index_kit_id, library_type_id=library_type_id,
    )
    self._session.add(index_kit_library_type_link)
    self._session.commit()
    self._session.refresh(index_kit_library_type_link)

    if not persist_session:
        self.close_session()

    return index_kit_library_type_link


def unlink_library_sample(
    self, library_id: int, sample_id: int,
    commit: bool = True
) -> None:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (_ := self._session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")
    
    if (_ := self._session.get(models.Sample, sample_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Sample with id {sample_id} does not exist")

    if (links := self._session.query(models.LibrarySampleLink).where(
        models.LibrarySampleLink.library_id == library_id,
        models.LibrarySampleLink.sample_id == sample_id
    ).all()) is None:
        raise exceptions.LinkDoesNotExist(f"Library with id {library_id} and sample with id {sample_id} are not linked")
    
    for link in links:
        self._session.delete(link)

    if commit:
        self._session.commit()

    if not persist_session:
        self.close_session()


def link_library_seq_request(
    self, library_id: int, seq_request_id: int,
    commit: bool = True
) -> models.LibrarySeqRequestLink:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (_ := self._session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")
    if (_ := self._session.get(models.SeqRequest, seq_request_id)) is None:
        raise exceptions.ElementDoesNotExist(f"SeqRequest with id {seq_request_id} does not exist")

    if self._session.query(models.LibrarySeqRequestLink).where(
        models.LibrarySeqRequestLink.library_id == library_id,
        models.LibrarySeqRequestLink.seq_request_id == seq_request_id,
    ).first():
        raise exceptions.LinkAlreadyExists(f"Library with id {library_id} and SeqRequest with id {seq_request_id} are already linked")

    library_seq_request_link = models.LibrarySeqRequestLink(
        library_id=library_id, seq_request_id=seq_request_id,
    )
    self._session.add(library_seq_request_link)

    if commit:
        self._session.commit()
        self._session.refresh(library_seq_request_link)

    if not persist_session:
        self.close_session()

    return library_seq_request_link


def unlink_library_seq_request(
    self, library_id: int, seq_request_id: int,
    commit: bool = True
) -> None:
    
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (_ := self._session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")
    if (_ := self._session.get(models.SeqRequest, seq_request_id)) is None:
        raise exceptions.ElementDoesNotExist(f"SeqRequest with id {seq_request_id} does not exist")
    
    if (links := self._session.query(models.LibrarySeqRequestLink).where(
        models.LibrarySeqRequestLink.library_id == library_id,
        models.LibrarySeqRequestLink.seq_request_id == seq_request_id,
    ).all()) is None:
        raise exceptions.LinkDoesNotExist(f"Library with id {library_id} and SeqRequest with id {seq_request_id} are not linked")
    
    for link in links:
        self._session.delete(link)

    if commit:
        self._session.commit()

    if not persist_session:
        self.close_session()