"""Request review: submit, accept, return, reject, archive."""
from ._common import *  # noqa: F401,F403
from ._common import collect

SUBMITTABLE = rules.Predicate("request is submittable (auth form uploaded, libraries annotated)", lambda session, req: req.is_submittable())

SUBMIT = operation(
    "request.submit", "Submit request", K.ACTION, E.SEQ_REQUEST,
    effect(E.SEQ_REQUEST, RQ.DRAFT, RQ.SUBMITTED),
    effect(E.LIBRARY, LB.DRAFT, LB.SUBMITTED, via="libraries"),
    effect(E.POOL, PL.DRAFT, PL.SUBMITTED, via="pools"),
    guard=rules.StatusIn(frozenset([RQ.DRAFT])) & SUBMITTABLE,
    where=[B + "forms/actions/SubmitSeqRequestAction.py", DB + "core/actions.py:submit_seq_request"],
)

_REVIEW_GUARD = rules.StatusIn(frozenset([RQ.SUBMITTED]))
_REVIEW_WHERE = [B + "forms/actions/ProcessSeqRequestAction.py", DB + "core/actions.py:process_seq_request"]
_NO_SRC_CHECK = "no check on the request's current status"

ACCEPT = operation(
    "request.accept", "Accept request", K.ACTION, E.SEQ_REQUEST,
    effect(E.SEQ_REQUEST, ANY, RQ.ACCEPTED),
    effect(E.SAMPLE, SA.DRAFT, SA.WAITING_DELIVERY, via="samples"),
    effect(E.LIBRARY, LB.SUBMITTED, LB.ACCEPTED, via="libraries"),
    effect(E.LIBRARY, ANY, LB.POOLED, via="libraries", when="library is in a pool",
           gap="no status check: can move SEQUENCED or FAILED libraries back to POOLED"),
    effect(E.POOL, PL.SUBMITTED, PL.ACCEPTED, via="pools"),
    effect(E.PROJECT, ANY, PJ.PROCESSING, via="samples.project", gap="no status check: re-opens DELIVERED or ARCHIVED projects"),
    guard=_REVIEW_GUARD, where=_REVIEW_WHERE, gap=_NO_SRC_CHECK,
)

RETURN = operation(
    "request.return", "Return request for revision", K.ACTION, E.SEQ_REQUEST,
    effect(E.SEQ_REQUEST, ANY, RQ.DRAFT),
    effect(E.LIBRARY, LB.SUBMITTED, LB.DRAFT, via="libraries"),
    effect(E.POOL, PL.SUBMITTED, PL.DRAFT, via="pools"),
    guard=_REVIEW_GUARD, where=_REVIEW_WHERE, gap=_NO_SRC_CHECK,
)

REJECT = operation(
    "request.reject", "Reject request", K.ACTION, E.SEQ_REQUEST,
    effect(E.SEQ_REQUEST, ANY, RQ.REJECTED),
    effect(E.LIBRARY, LB.SUBMITTED, LB.REJECTED, via="libraries"),
    effect(E.POOL, PL.SUBMITTED, PL.REJECTED, via="pools"),
    guard=_REVIEW_GUARD, where=_REVIEW_WHERE, gap=_NO_SRC_CHECK,
)

ARCHIVE = operation(
    "request.archive", "Archive request", K.ACTION, E.SEQ_REQUEST,
    effect(E.SEQ_REQUEST, ANY, RQ.ARCHIVED),
    where=[B + "routes/htmx/seq_requests.py:archive_seq_request"],
    doc="DRAFT requests need WRITE access, all others INSIDER.",
)

UNARCHIVE = operation(
    "request.unarchive", "Unarchive request", K.ACTION, E.SEQ_REQUEST,
    effect(E.SEQ_REQUEST, ANY, RQ.DRAFT, gap="no check that the request is ARCHIVED; previous status is lost"),
    guard=rules.StatusIn(frozenset([RQ.ARCHIVED])),
    where=[B + "routes/htmx/seq_requests.py:unarchive_seq_request"],
)

ALL = collect(globals())
