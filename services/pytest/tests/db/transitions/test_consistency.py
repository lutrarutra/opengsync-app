from opengsync_db import SyncSession
from opengsync_db.categories import LibraryStatus as LB, SeqRequestStatus as RQ
from opengsync_db.transitions import consistency

from ..create_units import create_user, create_seq_request, create_library, create_lab_prep


def _ids(findings, invariant_id: str) -> tuple[int, ...]:
    return next((f.sample_ids for f in findings if f.invariant.id == invariant_id), ())


def test_clean_data_has_no_findings(session: SyncSession):
    user = create_user(session)
    seq_request = create_seq_request(session, user)
    create_library(session, user, seq_request)
    session.commit()
    assert consistency.check(session) == []
    assert consistency.format_report([]) == "No inconsistencies found."


def test_findings(session: SyncSession):
    user = create_user(session)
    prepared = create_seq_request(session, user)
    prepared.status = RQ.PREPARED
    library = create_library(session, user, prepared)
    library.status = LB.ACCEPTED
    lab_prep = create_lab_prep(session, user)
    library.lab_prep_id = lab_prep.id
    in_prep_stored = create_library(session, user, prepared)
    in_prep_stored.status = LB.POOLED
    in_prep_stored.lab_prep_id = lab_prep.id
    session.commit()

    findings = consistency.check(session)
    assert _ids(findings, "request_prepared_libraries_pooled") == (prepared.id,)
    assert _ids(findings, "library_in_prep_preparing") == (library.id,)
    report = consistency.format_report(findings)
    assert "[library_in_prep_preparing] 1 library records violate" in report
    assert "d9685235" in report
