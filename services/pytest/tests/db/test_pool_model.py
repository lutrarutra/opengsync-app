from opengsync_db import SyncSession, actions, queries as Q

from .create_units import (
    create_user, create_seq_request, create_library, create_pool
)


def test_pool_model(session: SyncSession):
    user = create_user(session)
    seq_request = create_seq_request(session, user)

    pools = [
        create_pool(session, user, seq_request),
        create_pool(session, user, seq_request),
        create_pool(session, user, seq_request),
    ]

    assert session.count(Q.pool.select()) == 3

    for pool in pools:
        for i in range(2):
            actions.dilute_pool(session, pool, i, user.id, None)

    assert session.count(Q.pool.select()) == 3
    
    for pool in pools:
        session.refresh(pool)
        assert len(pool.dilutions) == 2
        for i in range(10):
            library = create_library(session, user, seq_request)
            library.pool_id = pool.id

    assert session.count(Q.pool.select()) == 3
    assert session.count(Q.library.select()) == 3 * 10

    for pool in pools:
        session.refresh(pool)
        assert pool.num_libraries == 10
        assert len(pool.libraries) == 10
        assert len(pool.dilutions) == 2

    merged = create_pool(session, user, seq_request)

    actions.merge_pools(session, merged_pool=merged, pools=pools)

    assert session.count(Q.pool.select()) == 4

    session.refresh(merged)
    assert merged.num_libraries == 30
    assert len(merged.libraries) == 30
    assert len(merged.dilutions) == 0

    session.delete(merged, flush=True)
    assert session.count(Q.pool.select()) == 3
    assert session.count(Q.library.select()) == 30

    
