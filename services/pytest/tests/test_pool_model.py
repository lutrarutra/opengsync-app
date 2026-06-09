from opengsync_db import SyncDBHandler, queries as Q

from .create_units import (
    create_user, create_seq_request, create_library, create_pool
)


def test_pool_model(db: SyncDBHandler):
    user = create_user(db)
    seq_request = create_seq_request(db, user)

    pools = [
        create_pool(db, user, seq_request),
        create_pool(db, user, seq_request),
        create_pool(db, user, seq_request),
    ]

    assert db.session.count(Q.pool.select()) == 3

    for pool in pools:
        for i in range(2):
            db.actions.dilute_pool(pool, i, user.id, None)

    assert db.session.count(Q.pool.select()) == 3
    
    for pool in pools:
        db.session.refresh(pool)
        assert len(pool.dilutions) == 2
        for i in range(10):
            library = create_library(db, user, seq_request)
            library.pool_id = pool.id

    assert db.session.count(Q.pool.select()) == 3
    assert db.session.count(Q.library.select()) == 3 * 10

    for pool in pools:
        db.session.refresh(pool)
        assert pool.num_libraries == 10
        assert len(pool.libraries) == 10
        assert len(pool.dilutions) == 2

    merged = create_pool(db, user, seq_request)

    db.actions.merge_pools(merged_pool=merged, pools=pools)

    assert db.session.count(Q.pool.select()) == 4

    db.session.refresh(merged)
    assert merged.num_libraries == 30
    assert len(merged.libraries) == 30
    assert len(merged.dilutions) == 0

    db.session.delete(merged, flush=True)
    assert db.session.count(Q.pool.select()) == 3
    assert db.session.count(Q.library.select()) == 30

    
