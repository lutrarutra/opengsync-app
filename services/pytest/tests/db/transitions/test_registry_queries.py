from opengsync_db.categories import (
    LibraryStatus as LB, ProjectStatus as PJ, SeqRequestStatus as RQ, SampleStatus as SA, PoolStatus as PL,
)
from opengsync_db.transitions import ANY, at_least, below, registry
from opengsync_db.transitions import entities as E
from opengsync_db.transitions.core import spec_str


def test_operations_reaching_prepared_lists_all_ways():
    ids = {op.id for op in registry().operations_reaching(E.SEQ_REQUEST, RQ.PREPARED)}
    assert ids == {"receipt.store_samples", "prep.pool_libraries", "prep.complete", "worker.request_prepared"}


def test_operations_reaching_with_source():
    ids = {op.id for op in registry().operations_reaching(E.SEQ_REQUEST, RQ.PREPARED, RQ.SAMPLES_RECEIVED)}
    # pool_libraries only moves ACCEPTED requests
    assert "prep.pool_libraries" not in ids
    assert {"worker.request_prepared", "prep.complete", "receipt.store_samples"} <= ids


def test_operations_reaching_includes_manual_edits_but_not_migrations():
    ids = {op.id for op in registry().operations_reaching(E.LIBRARY, LB.REMOVED)}
    assert ids == {"manual.edit_library", "mux.sample_pooling"}


def test_outgoing_from_accepted_request():
    outgoing = {dst: {op.id for op in ops} for dst, ops in registry().outgoing(E.SEQ_REQUEST, RQ.ACCEPTED).items()}
    assert outgoing[RQ.SAMPLES_RECEIVED] == {"receipt.store_samples", "worker.request_samples_received"}
    assert outgoing[RQ.PREPARED] == {"receipt.store_samples", "prep.pool_libraries", "prep.complete"}
    assert outgoing[RQ.REJECTED] == {"request.reject"}
    assert RQ.ACCEPTED not in outgoing


def test_allows():
    reg = registry()
    submit = reg["request.submit"]
    assert reg.allows(submit, E.SEQ_REQUEST, RQ.DRAFT, RQ.SUBMITTED)
    assert not reg.allows(submit, E.SEQ_REQUEST, RQ.ACCEPTED, RQ.SUBMITTED)
    assert reg.allows(submit, E.LIBRARY, LB.DRAFT, LB.SUBMITTED)
    assert not reg.allows(submit, E.PROJECT, PJ.DRAFT, PJ.PROCESSING)

    accept = reg["request.accept"]
    # no source check on the request itself (documented gap)
    assert reg.allows(accept, E.SEQ_REQUEST, RQ.FINISHED, RQ.ACCEPTED)
    assert reg.allows(accept, E.SAMPLE, SA.DRAFT, SA.WAITING_DELIVERY)
    assert not reg.allows(accept, E.SAMPLE, SA.STORED, SA.WAITING_DELIVERY)


def test_creation_effects():
    reg = registry()
    assert reg.allows(reg["request.create"], E.SEQ_REQUEST, None, RQ.DRAFT)
    assert not reg.allows(reg["request.create"], E.SEQ_REQUEST, RQ.DRAFT, RQ.DRAFT)
    # chosen status
    assert reg.allows(reg["pool.create"], E.POOL, None, PL.STORED)


def test_legacy_status_order_semantics():
    # ids >= 10 (FAILED, REJECTED, ARCHIVED, ...) are never "below" and always "at least"
    assert LB.FAILED not in below(LB.SEQUENCED)
    assert LB.FAILED in at_least(LB.POOLED)
    assert LB.PREPARING in below(LB.STORED)


def test_spec_str():
    assert spec_str(ANY) == "any"
    assert spec_str(at_least(LB.POOLED)) == "≥ POOLED"
    assert spec_str(below(LB.SEQUENCED)) == "< SEQUENCED"
    assert spec_str(frozenset([LB.STORED, LB.ACCEPTED])) == "ACCEPTED, STORED"
    assert spec_str(frozenset([None, PJ.DRAFT])) == "new, DRAFT"


def test_gaps_are_collected():
    gaps = dict(registry().gaps())
    assert "receipt.store_samples" in gaps
    assert "Request FAILED" in gaps
    assert any(where.startswith("request.accept (") for where in gaps)
