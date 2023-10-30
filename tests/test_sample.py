import pytest

from limbless import models
from limbless.core import exceptions, DBHandler

@pytest.fixture(scope="function", autouse=True)
def db_handler():
    return DBHandler(":memory:")

@pytest.fixture(scope="function", autouse=True)
def project(db_handler):
    return db_handler.create_project(
        name="project",
        description="description",
    )

def test_create_sample(db_handler, project):
    sample = db_handler.create_sample(
        name="sample",
        organism="organism",
        index1="index1",
        index2="index2"
    )
    assert sample.id is not None
    assert sample.name == "sample"
    assert sample.organism == "organism"
    assert sample.index1 == "index1"
    assert sample.index2 == "index2"

    samples, _ = db_handler.get_samples()
    assert len(samples) == 1
    assert samples[0] == sample

def test_get_sample(db_handler):
    sample = db_handler.create_sample(
        name="sample",
        organism="organism",
        index1="index1",
        index2="index2"
    )
    q_sample = db_handler.get_sample(sample.id)
    assert q_sample == sample

def test_update_sample(db_handler):
    sample = db_handler.create_sample(
        name="sample",
        organism="organism",
        index1="index1",
        index2="index2"
    )
    sample.name = "sample2"
    sample.organism = "organism2"
    sample.index1 = "index12"
    sample.index2 = "index22"
    db_handler.update_sample(sample.id, name="sample2", organism="organism2", index1="index12", index2="index22")
    assert sample.name == "sample2"
    assert sample.organism == "organism2"
    assert sample.index1 == "index12"
    assert sample.index2 == "index22"

    # Non existent sample_id
    with pytest.raises(exceptions.ElementDoesNotExist):
        db_handler.update_sample(-1, name="sample2", organism="organism2", index1="index12", index2="index22")

def test_delete_sample(db_handler):
    sample = db_handler.create_sample(
        name="sample",
        organism="organism",
        index1="index1",
        index2="index2"
    )
    db_handler.delete_sample(sample.id)
    assert db_handler.get_sample(sample.id) is None

    # Non existent sample_id
    with pytest.raises(exceptions.ElementDoesNotExist):
        db_handler.delete_sample(-1)

def test_duplicate_sample(db_handler):
    # Duplicate sample name (allowed in different projects)
    sample1 = db_handler.create_sample(
        name="duplicate.sample",
        organism="organism",
        index1="index1",
        index2="index2"
    )
    sample2 = db_handler.create_sample(
        name="duplicate.sample",
        organism="organism",
        index1="index1",
        index2="index2"
    )
    assert db_handler.get_sample(sample1.id) is not None
    assert db_handler.get_sample(sample2.id) is not None