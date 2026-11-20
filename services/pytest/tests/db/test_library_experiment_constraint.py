"""A library is in an experiment only through its pool.

library.experiment_id duplicates pool.experiment_id. The database enforces that they agree:
- fk_library_pool_experiment: (pool_id, experiment_id) -> pool (id, experiment_id), ON UPDATE CASCADE
- ck_library_experiment_requires_pool: an unpooled library is in no experiment

Regression: removing all libraries from a pool (and lab prep re-pooling, pool merging) left the
libraries in the pool's experiment after they had left the pool.
"""
import pytest
import sqlalchemy as sa

from opengsync_db import SyncSession, models, actions, exceptions, queries as Q, categories as C

from .create_units import create_user, create_seq_request, create_library, create_pool, create_experiment

WORKFLOW = C.ExperimentWorkFlow.NOVASEQ_6K_S1_STD


class Setup:
    """Pool ``linked`` (in ``experiment``) and pool ``free`` (in none), with one library each."""

    def __init__(self, session: SyncSession):
        self.session = session
        user = create_user(session)
        self.seq_request = create_seq_request(session, user)
        self.experiment = create_experiment(session, user, WORKFLOW)
        self.other_experiment = create_experiment(session, user, WORKFLOW)
        self.linked = create_pool(session, user, self.seq_request)
        self.free = create_pool(session, user, self.seq_request)
        self.linked_library = create_library(session, user, self.seq_request)
        self.free_library = create_library(session, user, self.seq_request)
        self.linked_library.pool_id = self.linked.id
        self.free_library.pool_id = self.free.id
        session.flush()
        session.refresh(self.linked)
        actions.link_pool_experiment(session, self.experiment, self.linked)
        session.commit()

    def execute(self, sql: str, **params):
        self.session.execute(sa.text(sql), params)
        self.session.flush()

    def experiment_of(self, library: models.Library) -> int | None:
        self.session.expire_all()
        return self.session.get_one(Q.library.select(id=library.id)).experiment_id


@pytest.fixture
def setup(session: SyncSession) -> Setup:
    return Setup(session)


def test_linking_puts_the_libraries_in_the_experiment(setup: Setup):
    assert setup.experiment_of(setup.linked_library) == setup.experiment.id
    assert setup.experiment_of(setup.free_library) is None


def test_unpooled_library_cannot_be_in_an_experiment(setup: Setup):
    with pytest.raises(sa.exc.IntegrityError, match="ck_library_experiment_requires_pool"):
        setup.execute("UPDATE library SET pool_id = NULL WHERE id = :id", id=setup.linked_library.id)


def test_library_cannot_be_in_an_experiment_its_pool_is_not_in(setup: Setup):
    with pytest.raises(sa.exc.IntegrityError, match="fk_library_pool_experiment"):
        setup.execute("UPDATE library SET experiment_id = :e WHERE id = :id", e=setup.experiment.id, id=setup.free_library.id)


def test_library_cannot_be_in_another_experiment_than_its_pool(setup: Setup):
    with pytest.raises(sa.exc.IntegrityError, match="fk_library_pool_experiment"):
        setup.execute("UPDATE library SET experiment_id = :e WHERE id = :id", e=setup.other_experiment.id, id=setup.linked_library.id)


def test_library_cannot_move_to_a_pool_in_another_experiment(setup: Setup):
    with pytest.raises(sa.exc.IntegrityError, match="fk_library_pool_experiment"):
        setup.execute("UPDATE library SET pool_id = :p WHERE id = :id", p=setup.free.id, id=setup.linked_library.id)


def test_pool_experiment_change_carries_its_libraries(setup: Setup):
    setup.execute("UPDATE pool SET experiment_id = :e WHERE id = :id", e=setup.other_experiment.id, id=setup.linked.id)
    assert setup.experiment_of(setup.linked_library) == setup.other_experiment.id

    setup.execute("UPDATE pool SET experiment_id = NULL WHERE id = :id", id=setup.linked.id)
    assert setup.experiment_of(setup.linked_library) is None


def test_set_library_pool_follows_the_pool(setup: Setup):
    library = setup.session.get_one(Q.library.select(id=setup.free_library.id))
    actions.set_library_pool(setup.session, library, setup.session.get_one(Q.pool.select(id=setup.linked.id)))
    setup.session.commit()
    assert setup.experiment_of(library) == setup.experiment.id

    library = setup.session.get_one(Q.library.select(id=library.id))
    actions.set_library_pool(setup.session, library, None)
    setup.session.commit()
    assert setup.experiment_of(library) is None
    assert setup.session.get_one(Q.library.select(id=library.id)).pool_id is None


def test_merging_a_pool_in_an_experiment_is_refused(setup: Setup):
    merged = create_pool(setup.session, setup.seq_request.requestor, setup.seq_request)
    with pytest.raises(exceptions.InvalidOperation, match="experiment"):
        actions.merge_pools(setup.session, merged_pool=merged, pools=[setup.linked, setup.free])
    setup.session.rollback()

    setup.session.expire_all()
    assert setup.session.get_one(Q.library.select(id=setup.linked_library.id)).pool_id == setup.linked.id
    assert setup.session.get_one(Q.library.select(id=setup.free_library.id)).pool_id == setup.free.id
