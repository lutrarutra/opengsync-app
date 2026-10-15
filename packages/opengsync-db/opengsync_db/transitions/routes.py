"""Routes: named paths a request takes through the operations, one per kind of submission.

The route of a request is inferred from its submission type (and re-sequencing libraries), unless
staff pinned another one (`SeqRequest.route_override`).
"""
from __future__ import annotations

from typing import Any

from ..categories import SeqRequestStatus as RQ, LibraryStatus as LB, SubmissionType
from .core import Route, Step, at_least
from . import entities as E
from . import relations as R
from . import rules

_DONE_REQUEST = frozenset([RQ.FINISHED, RQ.ARCHIVED])


def _request_reached(status: RQ) -> rules.Rule:
    """Request is at `status` or further along the normal flow (failed and rejected do not count)."""
    return rules.StatusIn(frozenset(s for s in RQ if s.id >= status.id and s not in (RQ.FAILED, RQ.REJECTED)))


SUBMIT = Step("submit", "Submit", ("request.submit",), _request_reached(RQ.SUBMITTED))
REVIEW = Step("review", "Review", ("request.accept", "request.return", "request.reject"), _request_reached(RQ.ACCEPTED))
RECEIVE = Step(
    "receive", "Receive samples", ("receipt.store_samples", "worker.request_samples_received"),
    _request_reached(RQ.SAMPLES_RECEIVED),
)
PREP = Step(
    "prep", "Library prep", ("prep.add_libraries", "prep.upload_table"),
    rules.ChildrenNone(R.REQUEST_LIBRARIES, frozenset([LB.DRAFT, LB.SUBMITTED, LB.ACCEPTED])) | _request_reached(RQ.PREPARED),
)
MUX = Step("mux", "Sample multiplexing", ("mux.sample_pooling",), _request_reached(RQ.PREPARED), optional=True)
POOL = Step(
    "pool", "Pool libraries", ("prep.pool_libraries", "prep.complete", "worker.request_prepared"),
    _request_reached(RQ.PREPARED),
)
SEQUENCE = Step(
    "sequence", "Sequencing",
    ("experiment.load_flowcell", "worker.rf_new_run", "worker.rf_run_finished", "api.lane_reads", "worker.request_data_processing"),
    _request_reached(RQ.DATA_PROCESSING),
)
RELEASE = Step(
    "release", "Release data", ("api.release_project", "project.share_data"),
    rules.ChildrenAll(R.REQUEST_LIBRARIES, at_least(LB.SHARED)) | rules.StatusIn(_DONE_REQUEST),
)
FINISH = Step("finish", "Finished", ("worker.request_finished",), rules.StatusIn(_DONE_REQUEST))

STORE_POOLS = Step(
    "receive", "Receive pools", ("receipt.store_samples",),
    _request_reached(RQ.PREPARED),
)
STORE_LIBRARIES = Step(
    "receive", "Receive libraries", ("receipt.store_samples",),
    _request_reached(RQ.SAMPLES_RECEIVED),
)
QC = Step(
    "qc", "Library QC", ("manual.edit_library",),
    rules.ChildrenNone(R.REQUEST_LIBRARIES, frozenset([LB.QC_PENDING])),
)
QC_ARCHIVE = Step("archive", "Archive", ("request.archive",), rules.StatusIn(frozenset([RQ.ARCHIVED])))
_IS_RESEQ = rules.Predicate(
    "request has open re-sequenced libraries next to sequenced ones", lambda session, req: is_reseq(session, req),
)
RESEQ_ADD = Step(
    "reseq", "Re-sequence libraries", ("library.reseq", "library.reseq_single", "worker.request_reopen"), _IS_RESEQ,
)


def _type(*types: SubmissionType) -> rules.Rule:
    return rules.SubmissionTypeIn(*types)


RAW_SAMPLES = Route(
    "raw_samples", "Raw samples, in-house library prep", E.SEQ_REQUEST, _type(SubmissionType.RAW_SAMPLES),
    (SUBMIT, REVIEW, RECEIVE, PREP, MUX, POOL, SEQUENCE, RELEASE, FINISH),
)
POOLED_LIBRARIES = Route(
    "pooled_libraries", "Pre-pooled libraries", E.SEQ_REQUEST, _type(SubmissionType.POOLED_LIBRARIES),
    (SUBMIT, REVIEW, STORE_POOLS, SEQUENCE, RELEASE, FINISH),
)
UNPOOLED_LIBRARIES = Route(
    "unpooled_libraries", "Un-pooled libraries, pooled in-house", E.SEQ_REQUEST, _type(SubmissionType.UNPOOLED_LIBRARIES),
    (SUBMIT, REVIEW, STORE_LIBRARIES, POOL, SEQUENCE, RELEASE, FINISH),
)
QC_ONLY = Route(
    "qc_only", "QC only", E.SEQ_REQUEST, _type(SubmissionType.QC_ONLY),
    (SUBMIT, REVIEW, STORE_LIBRARIES, QC, QC_ARCHIVE),
    doc="QC_COMPLETED is only set by hand until the QC workflow exists (docs/plans/qc-only-sequencing-request.md).",
)
RESEQ = Route(
    "reseq", "Re-sequencing", E.SEQ_REQUEST, _IS_RESEQ,
    (RESEQ_ADD, PREP, POOL, SEQUENCE, RELEASE, FINISH),
    doc="Inferred when the request has re-sequenced libraries (`original_library_id`) with open work next to sequenced ones.",
)

ROUTES: tuple[Route, ...] = (RAW_SAMPLES, POOLED_LIBRARIES, UNPOOLED_LIBRARIES, QC_ONLY, RESEQ)
BY_ID: dict[str, Route] = {r.id: r for r in ROUTES}
_BY_SUBMISSION_TYPE = {
    SubmissionType.RAW_SAMPLES: RAW_SAMPLES,
    SubmissionType.POOLED_LIBRARIES: POOLED_LIBRARIES,
    SubmissionType.UNPOOLED_LIBRARIES: UNPOOLED_LIBRARIES,
    SubmissionType.QC_ONLY: QC_ONLY,
}


def is_reseq(session: Any, seq_request: Any) -> bool:
    """The request has open re-sequenced libraries (`original_library_id`) next to already sequenced ones."""
    import sqlalchemy as sa
    from .. import models
    from .operations._common import OPEN_LIBRARY, SEQUENCED_LIBRARY

    def _exists(*conds):
        return sa.exists().where(models.Library.seq_request_id == seq_request.id, *conds)

    return bool(session.execute(sa.select(sa.and_(
        _exists(models.Library.original_library_id.is_not(None), models.Library.status.in_(list(OPEN_LIBRARY))),
        _exists(models.Library.status.in_(list(SEQUENCED_LIBRARY))),
    ))).scalar())


def infer_route(session: Any, seq_request: Any) -> Route:
    """Pinned route if set, re-sequencing if `is_reseq`, else by submission type."""
    override = getattr(seq_request, "route_override", None)
    if override is not None and override in BY_ID:
        return BY_ID[override]
    if seq_request.submission_type != SubmissionType.QC_ONLY and is_reseq(session, seq_request):
        return RESEQ
    return _BY_SUBMISSION_TYPE[seq_request.submission_type]
