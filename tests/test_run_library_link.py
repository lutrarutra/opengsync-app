import pytest

from limbless import models
from limbless.core import exceptions, DBHandler

@pytest.fixture(scope="function", autouse=True)
def db_handler():
    return DBHandler(":memory:")

def test_link_run_library(db_handler):
    run = db_handler.create_run(
        lane=1,
        r1_cycles=1, r2_cycles=2,
        i1_cycles=3, i2_cycles=4,
        experiment_id=1
    )
    assert len(db_handler.get_run_libraries(run.id)) == 0

    library = db_handler.create_library(
        name="library",
        library_type=models.LibraryType.TRANSCRIPTOME
    )
    assert len(db_handler.get_library_runs(library.id)) == 0

    run_library_link = db_handler.link_run_library(
        run.id, library.id
    )
    assert run_library_link is not None
    assert run_library_link.run_id == run.id
    assert run_library_link.library_id == library.id
    
    run_libraries = db_handler.get_run_libraries(run.id)
    assert len(run_libraries) == 1
    assert run_libraries[0] == library

    library_runs = db_handler.get_library_runs(library.id)
    assert len(library_runs) == 1
    assert library_runs[0] == run

    # Try non existent run
    with pytest.raises(exceptions.ElementDoesNotExist):
        db_handler.link_run_library(
            -1, library.id
        )

    # Try non existent library
    with pytest.raises(exceptions.ElementDoesNotExist):
        db_handler.link_run_library(
            run.id, -1
        )

    # Try duplicate link
    with pytest.raises(exceptions.LinkAlreadyExists):
        db_handler.link_run_library(
            run.id, library.id
        )

def test_unlink_run_library(db_handler):
    run = db_handler.create_run(
        lane=1,
        r1_cycles=1, r2_cycles=2,
        i1_cycles=3, i2_cycles=4,
        experiment_id=1
    )

    library = db_handler.create_library(
        name="library",
        library_type=models.LibraryType.TRANSCRIPTOME
    )

    run_library_link = db_handler.link_run_library(
        run.id, library.id
    )
    assert run_library_link is not None

    db_handler.unlink_run_library(run.id, library.id)
    assert len(db_handler.get_run_libraries(run.id)) == 0
    assert len(db_handler.get_library_runs(library.id)) == 0

    # Try non existent link
    with pytest.raises(exceptions.LinkDoesNotExist):
        db_handler.unlink_run_library(run.id, library.id)

    # Try non existent run
    with pytest.raises(exceptions.ElementDoesNotExist):
        db_handler.unlink_run_library(-1, library.id)

    # Try non existent library
    with pytest.raises(exceptions.ElementDoesNotExist):
        db_handler.unlink_run_library(run.id, -1)