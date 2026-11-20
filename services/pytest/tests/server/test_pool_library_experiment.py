"""Taking libraries out of / into a pool keeps library.experiment_id in step with the pool.

Regression: DELETE /htmx/pools/{id}/remove-libraries cleared pool_id but left the libraries in the
pool's experiment, and adding libraries to a pool already in an experiment never put them in it.
The database now refuses both (see tests/db/test_library_experiment_constraint.py).
"""
import json

import pytest
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, actions, queries as Q, categories as C

from ..db.create_units import create_experiment, create_library, create_pool, create_seq_request
from ._http import assert_flash, assert_htmx_redirect, delete, post_form

PREFIX = "/htmx/pools"
WORKFLOW = C.ExperimentWorkFlow.NOVASEQ_6K_S1_STD


class Setup:
    """A pool in an experiment with two libraries, and an unpooled library of the same request."""

    def __init__(self, session: SyncSession, user: models.User, insider: models.User):
        self.session = session
        seq_request = create_seq_request(session, user)
        self.experiment = create_experiment(session, insider, WORKFLOW)
        self.pool = create_pool(session, user, seq_request)
        self.libraries = [create_library(session, user, seq_request) for _ in range(2)]
        for library in self.libraries:
            library.pool_id = self.pool.id
        self.unpooled = create_library(session, user, seq_request)
        session.flush()
        session.refresh(self.pool)
        actions.link_pool_experiment(session, self.experiment, self.pool)
        session.commit()

    def reload(self, library: models.Library) -> models.Library:
        self.session.expire_all()
        return self.session.get_one(Q.library.select(id=library.id))


@pytest.fixture
def setup(session: SyncSession, user, insider) -> Setup:
    return Setup(session, user, insider)


def test_remove_all_libraries_takes_them_out_of_the_experiment(client: TestClient, setup: Setup, admin_token: str):
    response = delete(client, f"{PREFIX}/{setup.pool.id}/remove-libraries", admin_token, htmx=True)

    assert_htmx_redirect(response, f"/pools/{setup.pool.id}")
    for library in setup.libraries:
        library = setup.reload(library)
        assert library.pool_id is None
        assert library.experiment_id is None


def test_remove_library_takes_it_out_of_the_experiment(client: TestClient, setup: Setup, admin_token: str):
    removed, kept = setup.libraries

    response = delete(client, f"{PREFIX}/{setup.pool.id}/remove-library/{removed.id}", admin_token, htmx=True)

    assert response.status_code == 204, response.text
    assert_flash(response, f"Library {removed.name} removed from pool", "success")
    assert (setup.reload(removed).pool_id, setup.reload(removed).experiment_id) == (None, None)
    assert (setup.reload(kept).pool_id, setup.reload(kept).experiment_id) == (setup.pool.id, setup.experiment.id)


def test_remove_library_not_in_the_pool_is_404(client: TestClient, setup: Setup, admin_token: str):
    response = delete(client, f"{PREFIX}/{setup.pool.id}/remove-library/{setup.unpooled.id}", admin_token, htmx=True)

    assert response.status_code == 404


def test_library_added_to_a_pool_in_an_experiment_joins_it(client: TestClient, setup: Setup, insider_token: str):
    response = post_form(
        client, f"/htmx/actions/select-pool-libraries/{setup.pool.id}",
        {"selected_library_ids": json.dumps([setup.unpooled.id])}, token=insider_token,
    )

    assert_htmx_redirect(response, f"/pools/{setup.pool.id}")
    library = setup.reload(setup.unpooled)
    assert (library.pool_id, library.experiment_id) == (setup.pool.id, setup.experiment.id)
