"""Library experiment follows pool migration (f3a91c5d7e20).

Like test_sample_submission_layout_migration: the database is cloned from the test template (current
models), the constraints are dropped, the previous revision is stamped and the migration must recreate
exactly what the models define. It first syncs drifted library.experiment_id values to the pools.
"""
import sqlalchemy as sa
from alembic import command

from opengsync_db import SyncSession, actions, categories as C

from ..db.create_units import create_user, create_seq_request, create_library, create_pool, create_experiment
from .test_checklist_log_migration import engine  # noqa: F401 (fixture)
from .test_status_history_migration import _config

REVISION = "f3a91c5d7e20"
PREVIOUS = "e2b6f8a1c437"


def _schema(connection: sa.Connection) -> dict:
    inspector = sa.inspect(connection)
    return {
        "library_foreign_keys": {
            (fk["name"], tuple(fk["constrained_columns"]), fk["referred_table"], tuple(fk["referred_columns"]),
             fk["options"].get("onupdate"), fk["options"].get("ondelete"))
            for fk in inspector.get_foreign_keys("library")
        },
        "library_checks": {(ck["name"], ck["sqltext"]) for ck in inspector.get_check_constraints("library")},
        "pool_unique": {(uc["name"], tuple(uc["column_names"])) for uc in inspector.get_unique_constraints("pool")},
    }


def _drop_constraints(conn: sa.Connection) -> None:
    conn.execute(sa.text("ALTER TABLE library DROP CONSTRAINT ck_library_experiment_requires_pool"))
    conn.execute(sa.text("ALTER TABLE library DROP CONSTRAINT fk_library_pool_experiment"))
    conn.execute(sa.text("ALTER TABLE pool DROP CONSTRAINT uq_pool_id_experiment_id"))


def test_migration_matches_models(engine: sa.Engine):  # noqa: F811
    with engine.connect() as conn:
        expected = _schema(conn)
        assert ("fk_library_pool_experiment", ("pool_id", "experiment_id"), "pool", ("id", "experiment_id"), "CASCADE", None) in expected["library_foreign_keys"]
        _drop_constraints(conn)
        conn.commit()
        command.stamp(_config(conn), PREVIOUS)
        conn.commit()

        command.upgrade(_config(conn), REVISION)
        conn.commit()
        assert _schema(conn) == expected

        command.downgrade(_config(conn), PREVIOUS)
        conn.commit()
        downgraded = _schema(conn)
        assert not any(fk[0] == "fk_library_pool_experiment" for fk in downgraded["library_foreign_keys"])
        assert not any(ck[0] == "ck_library_experiment_requires_pool" for ck in downgraded["library_checks"])
        assert ("uq_pool_id_experiment_id", ("id", "experiment_id")) not in downgraded["pool_unique"]


def test_migration_syncs_drifted_libraries_to_their_pools(session: SyncSession):
    user = create_user(session)
    seq_request = create_seq_request(session, user)
    experiment = create_experiment(session, user, C.ExperimentWorkFlow.NOVASEQ_6K_S1_STD)
    other = create_experiment(session, user, C.ExperimentWorkFlow.NOVASEQ_6K_S1_STD)
    linked = create_pool(session, user, seq_request)
    free = create_pool(session, user, seq_request)
    libraries = {name: create_library(session, user, seq_request) for name in ("orphan", "missing", "wrong", "stray", "ok")}
    for name in ("orphan", "missing", "wrong", "ok"):
        libraries[name].pool_id = linked.id
    libraries["stray"].pool_id = free.id
    session.flush()
    session.refresh(linked)
    actions.link_pool_experiment(session, experiment, linked)
    session.commit()
    ids = {name: library.id for name, library in libraries.items()}

    with session.get_bind().connect() as conn:
        _drop_constraints(conn)
        # The drift the old code left: removed from the pool but still in the experiment; added to a pool
        # in an experiment without it; in another experiment than the pool; in an experiment, pool in none
        conn.execute(sa.text("UPDATE library SET pool_id = NULL WHERE id = :id"), {"id": ids["orphan"]})
        conn.execute(sa.text("UPDATE library SET experiment_id = NULL WHERE id = :id"), {"id": ids["missing"]})
        conn.execute(sa.text("UPDATE library SET experiment_id = :e WHERE id = :id"), {"e": other.id, "id": ids["wrong"]})
        conn.execute(sa.text("UPDATE library SET experiment_id = :e WHERE id = :id"), {"e": experiment.id, "id": ids["stray"]})
        conn.commit()
        command.stamp(_config(conn), PREVIOUS)
        conn.commit()

        command.upgrade(_config(conn), REVISION)
        conn.commit()

        rows = dict(conn.execute(sa.text("SELECT id, experiment_id FROM library WHERE id = ANY(:ids)"), {"ids": list(ids.values())}).all())

    assert rows == {
        ids["orphan"]: None,
        ids["missing"]: experiment.id,
        ids["wrong"]: experiment.id,
        ids["stray"]: None,
        ids["ok"]: experiment.id,
    }
