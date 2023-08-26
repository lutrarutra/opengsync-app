import pytest

from limbless import models
from limbless.core import exceptions, DBHandler

@pytest.fixture(scope="function", autouse=True)
def db_handler():
    return DBHandler(":memory:")

def test_link_library_sample(db_handler):
    library = db_handler.create_library(
        name="library",
        library_type=models.LibraryType.TRANSCRIPTOME
    )
    assert len(db_handler.get_library_samples(library.id)) == 0

    sample = db_handler.create_sample(
        name="sample",
        organism="organism",
        index1="index1",
        index2="index2"
    )
    assert len(db_handler.get_sample_libraries(sample.id)) == 0

    library_sample_link = db_handler.link_library_sample(
        library.id, sample.id
    )
    assert library_sample_link is not None
    assert library_sample_link.library_id == library.id
    assert library_sample_link.sample_id == sample.id

    library_samples = db_handler.get_library_samples(library.id)
    assert len(library_samples) == 1
    assert library_samples[0] == sample

    sample_libraries = db_handler.get_sample_libraries(sample.id)
    assert len(sample_libraries) == 1
    assert sample_libraries[0] == library

    # Try non existent library
    with pytest.raises(exceptions.ElementDoesNotExist):
        db_handler.link_library_sample(
            -1, sample.id
        )

    # Try non existent sample
    with pytest.raises(exceptions.ElementDoesNotExist):
        db_handler.link_library_sample(
            library.id, -1
        )

    # Try duplicate link
    with pytest.raises(exceptions.LinkAlreadyExists):
        db_handler.link_library_sample(
            library.id, sample.id
        )

def test_unlink_library_sample(db_handler):
    library = db_handler.create_library(
        name="library",
        library_type=models.LibraryType.TRANSCRIPTOME
    )
    assert len(db_handler.get_library_samples(library.id)) == 0

    sample = db_handler.create_sample(
        name="sample",
        organism="organism",
        index1="index1",
        index2="index2"
    )
    assert len(db_handler.get_sample_libraries(sample.id)) == 0

    library_sample_link = db_handler.link_library_sample(
        library.id, sample.id
    )
    assert library_sample_link is not None

    db_handler.unlink_library_sample(library.id, sample.id)
    assert len(db_handler.get_library_samples(library.id)) == 0
    assert len(db_handler.get_sample_libraries(sample.id)) == 0

    # Try non existent link
    with pytest.raises(exceptions.LinkDoesNotExist):
        db_handler.unlink_library_sample(library.id, sample.id)

    # Try non existent library
    with pytest.raises(exceptions.ElementDoesNotExist):
        db_handler.unlink_library_sample(-1, sample.id)

    # Try non existent sample
    with pytest.raises(exceptions.ElementDoesNotExist):
        db_handler.unlink_library_sample(library.id, -1)
