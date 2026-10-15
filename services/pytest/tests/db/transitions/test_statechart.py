from opengsync_db import SyncSession
from opengsync_db.categories import LibraryStatus as LB, SeqRequestStatus as RQ, PrepStatus as PR, SubmissionType
from opengsync_db.transitions import run_operation, statechart, status

from ..create_units import create_user, create_seq_request, create_library, create_lab_prep


def _chart(session: SyncSession, obj):
    return statechart.build(status.build(session, obj), status.history(session, obj))


def _transitions(chart):
    return {(t.source.name, t.target.name): t for t in chart.transitions}


def test_request_chart_shape(session: SyncSession):
    user = create_user(session)
    seq_request = create_seq_request(session, user, submission_type=SubmissionType.RAW_SAMPLES)
    seq_request.status = RQ.SUBMITTED
    session.commit()
    chart = _chart(session, seq_request)

    cards = {c.status: c for c in chart.cards}
    assert cards[RQ.SUBMITTED].current
    assert RQ.FAILED not in cards  # nothing reaches it
    assert cards[RQ.REJECTED].side and not cards[RQ.ACCEPTED].side

    transitions = _transitions(chart)
    # accept / return / reject don't check the request status, but their guard says: from SUBMITTED
    assert {("SUBMITTED", "ACCEPTED"), ("SUBMITTED", "DRAFT"), ("SUBMITTED", "REJECTED")} <= set(transitions)
    assert ("FINISHED", "ACCEPTED") not in transitions
    # archive has no guard: only drawn from the current status
    assert ("SUBMITTED", "ARCHIVED") in transitions
    assert ("DRAFT", "ARCHIVED") not in transitions
    # completing a lab prep sets the request PREPARED without a status check, but that isn't how a
    # submitted request moves on: not drawn
    assert ("SUBMITTED", "PREPARED") not in transitions
    # worker rules are regular edges
    assert transitions[("SAMPLES_RECEIVED", "PREPARED")].actions[0].operation.id == "worker.request_prepared"


def test_states_of_current_edges(session: SyncSession):
    user = create_user(session)
    seq_request = create_seq_request(session, user, submission_type=SubmissionType.RAW_SAMPLES)
    seq_request.status = RQ.SAMPLES_RECEIVED
    library = create_library(session, user, seq_request)
    library.status = LB.ACCEPTED
    session.commit()
    transitions = _transitions(_chart(session, seq_request))

    worker = transitions[("SAMPLES_RECEIVED", "PREPARED")]
    assert worker.from_current
    assert worker.state == "blocked"
    assert worker.actions[0].blockers == (
        "1 libraries of the request below POOLED (1 ACCEPTED)",
        "none of the libraries of the request is POOLED",
    )
    assert transitions[("SAMPLES_RECEIVED", "ARCHIVED")].state == "available"
    assert transitions[("ACCEPTED", "SAMPLES_RECEIVED")].state == "inactive"


def test_path_taken_from_history(session: SyncSession):
    user = create_user(session)
    seq_request = create_seq_request(session, user)
    session.commit()
    with run_operation(session, "request.submit", subject=seq_request):
        seq_request.status = RQ.SUBMITTED
    with run_operation(session, "request.accept", subject=seq_request):
        seq_request.status = RQ.ACCEPTED
    session.commit()
    chart = _chart(session, seq_request)
    transitions = _transitions(chart)
    assert transitions[("DRAFT", "SUBMITTED")].taken and transitions[("SUBMITTED", "ACCEPTED")].taken
    assert not transitions[("SUBMITTED", "REJECTED")].taken
    cards = {c.status: c for c in chart.cards}
    assert cards[RQ.SUBMITTED].visited and cards[RQ.ACCEPTED].current and cards[RQ.ACCEPTED].since is not None


def test_lab_prep_chart(session: SyncSession):
    lab_prep = create_lab_prep(session, create_user(session))
    session.commit()
    chart = _chart(session, lab_prep)
    transitions = _transitions(chart)
    assert transitions[("PREPARING", "COMPLETED")].state == "available"
    assert {c.status for c in chart.cards} == {PR.PREPARING, PR.COMPLETED}
