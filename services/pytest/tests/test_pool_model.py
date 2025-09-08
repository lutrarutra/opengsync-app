from opengsync_db import DBHandler

from .create_units import (
    create_user, create_seq_request, create_library, create_pool
)


def test_pool_model(db: DBHandler):
    user = create_user(db)
    seq_request = create_seq_request(db, user)

    pools = [
        create_pool(db, user, seq_request),
        create_pool(db, user, seq_request),
        create_pool(db, user, seq_request),
    ]

    assert len(db.pools.find(limit=None)[0]) == 3

    for pool in pools:
        for i in range(2):
            db.pools.dilute(pool.id, i, user.id, None)

    assert len(db.pools.find(limit=None)[0]) == 3
    
    for pool in pools:
        db.refresh(pool)
        assert len(pool.dilutions) == 2
        for i in range(10):
            library = create_library(db, user, seq_request)
            db.libraries.add_to_pool(library.id, pool.id)

    assert len(db.pools.find(limit=None)[0]) == 3
    assert len(db.libraries.find(limit=None)[0]) == 3 * 10

    for pool in pools:
        db.refresh(pool)
        assert pool.num_libraries == 10
        assert len(pool.libraries) == 10
        assert len(pool.dilutions) == 2

    merged = create_pool(db, user, seq_request)

    db.pools.merge(
        merged_pool_id=merged.id,
        pool_ids=[pool.id for pool in pools],
    )

    assert len(db.pools.find(limit=None)[0]) == 1

    db.refresh(merged)
    assert merged.num_libraries == 30
    assert len(merged.libraries) == 30
    assert len(merged.dilutions) == 0

    db.pools.delete(merged.id)
    assert len(db.pools.find(limit=None)[0]) == 0
    assert len(db.libraries.find(limit=None)[0]) == 30

    
