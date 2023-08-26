import pytest

from limbless import models
from limbless.core import exceptions, DBHandler

@pytest.fixture(scope="function", autouse=True)
def db_handler():
    return DBHandler(":memory:")

def test_create_library(db_handler):
    library = db_handler.create_library(
        name="library",
        library_type=models.LibraryType.TRANSCRIPTOME,
    )

    assert library.id is not None
    assert library.name == "library"
    assert library.library_type == models.LibraryType.TRANSCRIPTOME

    libraries = db_handler.get_libraries()
    assert len(libraries) == 1
    assert libraries[0] == library

def test_get_library(db_handler):
    library = db_handler.create_library(
        name="library",
        library_type=models.LibraryType.TRANSCRIPTOME,
    )
    q_library = db_handler.get_library(library.id)
    assert library == q_library
    assert db_handler.get_library(-1) is None

def test_update_library(db_handler):
    library = db_handler.create_library(
        name="library",
        library_type=models.LibraryType.TRANSCRIPTOME,
    )
    db_handler.update_library(
        library.id, name="library2",
        library_type=models.LibraryType.CUSTOM_BARCODED_FEATURE
    )
    updated_library = db_handler.get_library(library.id)
    assert updated_library.name == "library2"
    assert updated_library.library_type == models.LibraryType.CUSTOM_BARCODED_FEATURE

    # Non existent library_id
    with pytest.raises(exceptions.ElementDoesNotExist):
        db_handler.update_library(
            -1, name="library2",
            library_type=models.LibraryType.CUSTOM_BARCODED_FEATURE
        )

def test_delete_library(db_handler):
    library = db_handler.create_library(
        name="library",
        library_type=models.LibraryType.TRANSCRIPTOME,
    )
    db_handler.delete_library(library.id)
    assert db_handler.get_library(library.id) is None

    # Non existent library_id
    with pytest.raises(exceptions.ElementDoesNotExist):
        db_handler.delete_library(-1)

def test_duplicate_library(db_handler):
    with pytest.raises(exceptions.NotUniqueValue):
        db_handler.create_library(
            name="library",
            library_type=models.LibraryType.TRANSCRIPTOME
        )
        db_handler.create_library(
            name="library",
            library_type=models.LibraryType.TRANSCRIPTOME,
        )