import pytest

from limbless import models
from limbless.core import exceptions, DBHandler

@pytest.fixture(scope="function", autouse=True)
def db_handler():
    return DBHandler(":memory:")

def test_create_experimet(db_handler):
    experiment = db_handler.create_experiment(
        flowcell="flowcell",
    )

    assert experiment.id is not None
    assert experiment.name == "experiment"
    assert experiment.flowcell == "flowcell"
    assert experiment.timestamp is not None

    experiments = db_handler.get_experiments()
    assert len(experiments) == 1
    assert experiments[0] == experiment

def test_get_experiment(db_handler):
    experiment = db_handler.create_experiment(
        flowcell="flowcell",
    )
    q_experiment = db_handler.get_experiment(experiment.id)

    assert experiment.id == q_experiment.id
    assert experiment.name == q_experiment.name
    assert experiment.flowcell == q_experiment.flowcell

    assert db_handler.get_experiment(-1) is None

def test_update_experiment(db_handler):
    experiment = db_handler.create_experiment(
        flowcell="flowcell",
    )

    db_handler.update_experiment(
        experiment.id, name="experiment_updated", flowcell="flowcell_updated"
    )
    updated_experiment = db_handler.get_experiment(experiment.id)
    assert updated_experiment.name == "experiment_updated"
    assert updated_experiment.flowcell == "flowcell_updated"

    db_handler.create_experiment(
        flowcell="flowcell",
    )

    with pytest.raises(exceptions.NotUniqueValue):
        db_handler.update_experiment(
            experiment.id,
            name="duplicate_name_rename_experiment"
        )

    # Non existent experiment_id
    with pytest.raises(exceptions.ElementDoesNotExist):
        db_handler.update_experiment(
            -1, name="experiment"
        )

def test_delete_experiment(db_handler):
    experiment = db_handler.create_experiment(
        name="experiment",
        flowcell="flowcell",
    )

    db_handler.delete_experiment(experiment.id)
    assert db_handler.get_experiment(experiment.id) is None

    # Non existent experiment_id
    with pytest.raises(exceptions.ElementDoesNotExist):
        db_handler.delete_experiment(-1)


def test_duplicate_experiment(db_handler):
    # Duplicate experiment name
    with pytest.raises(exceptions.NotUniqueValue):
        db_handler.create_experiment(
            name="experiment",
            flowcell="flowcell",
        )
        db_handler.create_experiment(
            name="experiment",
            flowcell="flowcell",
        )