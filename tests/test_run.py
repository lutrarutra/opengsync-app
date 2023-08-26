import pytest

from limbless import models
from limbless.core import exceptions, DBHandler

@pytest.fixture(scope="function", autouse=True)
def db_handler():
    return DBHandler(":memory:")

def test_create_run(db_handler):
    run = db_handler.create_run(
        lane=1,
        r1_cycles=1, r2_cycles=2,
        i1_cycles=3, i2_cycles=4,
        experiment_id=1
    )

    assert run.id is not None
    assert run.lane == 1
    assert run.r1_cycles == 1
    assert run.r2_cycles == 2
    assert run.i1_cycles == 3

def test_get_run(db_handler):
    run = db_handler.create_run(
        lane=1,
        r1_cycles=1, r2_cycles=2,
        i1_cycles=3, i2_cycles=4,
        experiment_id=1
    )
    q_run = db_handler.get_run(run.id)
    assert run == q_run
    assert db_handler.get_run(-1) is None

def test_update_run(db_handler):
    run = db_handler.create_run(
        lane=1,
        r1_cycles=1, r2_cycles=2,
        i1_cycles=3, i2_cycles=4,
        experiment_id=1
    )
    run.lane = 2
    run.r1_cycles = 2
    run.r2_cycles = 3
    run.i1_cycles = 4
    run.i2_cycles = 5
    db_handler.update_run(run.id, lane=2, r1_cycles=2, r2_cycles=3, i1_cycles=4, i2_cycles=5)
    assert run.lane == 2
    assert run.r1_cycles == 2
    assert run.r2_cycles == 3
    assert run.i1_cycles == 4
    assert run.i2_cycles == 5

    # Non existent run_id
    with pytest.raises(exceptions.ElementDoesNotExist):
        db_handler.update_run(-1, lane=2, r1_cycles=2, r2_cycles=3, i1_cycles=4, i2_cycles=5)

def test_delete_run(db_handler):
    run = db_handler.create_run(
        lane=1,
        r1_cycles=1, r2_cycles=2,
        i1_cycles=3, i2_cycles=4,
        experiment_id=1
    )
    db_handler.delete_run(run.id)
    assert db_handler.get_run(run.id) is None

    # Non-existent run
    with pytest.raises(exceptions.ElementDoesNotExist):
        db_handler.delete_run(-1)