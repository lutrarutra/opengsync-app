from typing import Optional, Union

from ... import models
from .. import exceptions
from ...models import categories

def create_library(
        self, name: str,
        library_type: categories.LibraryType,
        index_kit_id: int,
        commit: bool = True
    ) -> list[models.Library]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if self._session.query(models.Library).where(
        models.Library.name == name
    ).first() is not None:
        raise exceptions.NotUniqueValue(f"Library with name {name} already exists")
    
    if (index_kit := self._session.get(models.IndexKit, index_kit_id)) is None:
        raise exceptions.ElementDoesNotExist(f"IndexKit with id {index_kit_id} does not exist")

    library = models.Library(
        name=name,
        library_type_id=library_type.id,
        index_kit_id=index_kit_id
    )

    self._session.add(library)
    if commit:
        self._session.commit()
        self._session.refresh(library)

    if not persist_session: self.close_session()
    return library

def get_library(self, library_id: int) -> models.Library:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    library = self._session.get(models.Library, library_id)
    if not persist_session: self.close_session()
    return library

def get_libraries(self) -> list[models.Library]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    libraries = self._session.query(models.Library).all()
    if not persist_session: self.close_session()
    return libraries

def get_num_libraries(self) -> int:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.query(models.Library).count()
    if not persist_session: self.close_session()
    return res

def get_library_by_name(self, name: str) -> models.Library:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    library = self._session.query(models.Library).where(
        models.Library.name == name
    ).first()
    if not persist_session: self.close_session()
    return library

def delete_library(
        self, library_id: int,
        commit: bool = True
    ) -> None:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()
        
    library = self._session.get(models.Library, library_id)
    if not library:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")
    
    self._session.delete(library)
    if commit: self._session.commit()

    if not persist_session: self.close_session()

def update_library(
        self, library_id: int,
        name: Optional[str] = None,
        library_type: Optional[categories.LibraryType] = None,
        index_kit_id: Optional[int] = None,
        commit: bool = True
    ) -> models.Library:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    library = self._session.get(models.Library, library_id)
    if not library:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")
    
    if name is not None:
        _lib = self._session.query(models.Library).where(
            models.Library.name == name
        ).first()
        if _lib is not None and _lib.id != library_id:
            raise exceptions.NotUniqueValue(f"Library with name {name} already exists")

    if name is not None: library.name = name
    if library_type is not None:
        library.library_type_id = library_type.id
    if index_kit_id is not None:
        if self._session.get(models.IndexKit, index_kit_id) is None:
            raise exceptions.ElementDoesNotExist(f"IndexKit with id {index_kit_id} does not exist")
        library.index_kit_id = index_kit_id

    self._session.add(library)
    if commit:
        self._session.commit()
        self._session.refresh(library)

    if not persist_session: self.close_session()
    return library