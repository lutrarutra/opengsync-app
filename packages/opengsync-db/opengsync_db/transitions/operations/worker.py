"""Rules of the status worker (`update_statuses`, every few minutes), in execution order."""
from ._common import *  # noqa: F401,F403
from ._common import collect, OPEN_LIBRARY, SEQUENCED_LIBRARY

_SU = [W + "tasks/status_updater.py:update_statuses"]

EXPERIMENT_SEQUENCING = operation(
    "worker.experiment_sequencing", "Experiment is sequencing", K.WORKER, E.EXPERIMENT,
    effect(E.EXPERIMENT, ANY, EX.SEQUENCING, gap="overrides manual FAILED / CANCELED on every run"),
    reason="seq run of the experiment is RUNNING", where=_SU,
)

EXPERIMENT_RUN_FINISHED = operation(
    "worker.experiment_run_finished", "Experiment run finished", K.WORKER, E.EXPERIMENT,
    effect(E.EXPERIMENT, [EX.DRAFT, EX.LOADED, EX.SEQUENCING], [EX.SEQUENCED, EX.ARCHIVED], when="SEQUENCED for a FINISHED run, ARCHIVED for an ARCHIVED run"),
    guard=rules.StatusIn(frozenset([EX.DRAFT, EX.LOADED, EX.SEQUENCING])),
    reason="seq run of the experiment is FINISHED or ARCHIVED", where=_SU,
)

LIBRARY_SEQUENCED = operation(
    "worker.library_sequenced", "Library sequenced", K.WORKER, E.LIBRARY,
    effect(E.LIBRARY, below(LB.SEQUENCED), LB.SEQUENCED),
    reason="experiment of the library is SEQUENCED, DEMULTIPLEXED or ARCHIVED", where=_SU,
)

SAMPLE_STORED = operation(
    "worker.sample_stored", "Sample stored", K.WORKER, E.SAMPLE,
    effect(E.SAMPLE, SA.WAITING_DELIVERY, SA.STORED),
    reason="no library of the sample is below STORED", where=_SU,
)

POOL_SEQUENCED = operation(
    "worker.pool_sequenced", "Pool sequenced", K.WORKER, E.POOL,
    effect(E.POOL, [PL.ACCEPTED, PL.STORED], PL.SEQUENCED),
    reason="experiment of the pool is SEQUENCED, DEMULTIPLEXED or ARCHIVED", where=_SU,
)

REQUEST_REOPEN = operation(
    "worker.request_reopen", "Re-open request", K.WORKER, E.SEQ_REQUEST,
    effect(E.SEQ_REQUEST, [RQ.DATA_PROCESSING, RQ.FINISHED, RQ.ARCHIVED], RQ.SAMPLES_RECEIVED,
           gap="also re-opens requests that were archived by hand"),
    guard=rules.StatusIn(frozenset([RQ.DATA_PROCESSING, RQ.FINISHED, RQ.ARCHIVED])) & rules.ChildrenAny(R.REQUEST_LIBRARIES, OPEN_LIBRARY),
    reason="request has libraries with open work (ACCEPTED, PREPARING, STORED or POOLED), e.g. re-sequencing", where=_SU,
)

REQUEST_SAMPLES_RECEIVED = operation(
    "worker.request_samples_received", "Request samples received", K.WORKER, E.SEQ_REQUEST,
    effect(E.SEQ_REQUEST, RQ.ACCEPTED, RQ.SAMPLES_RECEIVED),
    guard=rules.All(
        rules.StatusIn(frozenset([RQ.ACCEPTED])),
        rules.ChildrenAll(R.REQUEST_SAMPLES, at_least(SA.STORED), nonempty=True),
        rules.ChildrenNone(R.REQUEST_LIBRARY_POOLS, below(PL.STORED)),
    ),
    reason="all samples of the request are stored and no library is in a pool below STORED", where=_SU,
)

REQUEST_PREPARED = operation(
    "worker.request_prepared", "Request prepared", K.WORKER, E.SEQ_REQUEST,
    effect(E.SEQ_REQUEST, RQ.SAMPLES_RECEIVED, RQ.PREPARED),
    guard=rules.All(
        rules.StatusIn(frozenset([RQ.SAMPLES_RECEIVED])),
        rules.ChildrenAll(R.REQUEST_LIBRARIES, at_least(LB.POOLED)),
        rules.ChildrenAny(R.REQUEST_LIBRARIES, frozenset([LB.POOLED])),
    ),
    reason="all libraries of the request are POOLED or beyond", where=_SU,
)

REQUEST_DATA_PROCESSING = operation(
    "worker.request_data_processing", "Request sequenced", K.WORKER, E.SEQ_REQUEST,
    effect(E.SEQ_REQUEST, [RQ.ACCEPTED, RQ.SAMPLES_RECEIVED, RQ.PREPARED], RQ.DATA_PROCESSING),
    guard=rules.All(
        rules.StatusIn(frozenset([RQ.ACCEPTED, RQ.SAMPLES_RECEIVED, RQ.PREPARED])),
        rules.ChildrenAll(R.REQUEST_LIBRARIES, at_least(LB.SEQUENCED)),
        rules.ChildrenAny(R.REQUEST_LIBRARIES, SEQUENCED_LIBRARY),
    ),
    reason="all libraries of the request are SEQUENCED or beyond", where=_SU,
)

PROJECT_REOPEN = operation(
    "worker.project_reopen", "Re-open project", K.WORKER, E.PROJECT,
    effect(E.PROJECT, [PJ.SEQUENCED, PJ.DELIVERED, PJ.ARCHIVED], PJ.PROCESSING),
    guard=rules.StatusIn(frozenset([PJ.SEQUENCED, PJ.DELIVERED, PJ.ARCHIVED])) & rules.ChildrenAny(R.PROJECT_LIBRARIES, OPEN_LIBRARY),
    reason="project has libraries with open work (ACCEPTED, PREPARING, STORED or POOLED)", where=_SU,
)

PROJECT_SEQUENCED = operation(
    "worker.project_sequenced", "Project sequenced", K.WORKER, E.PROJECT,
    effect(E.PROJECT, PJ.PROCESSING, PJ.SEQUENCED),
    guard=rules.All(
        rules.StatusIn(frozenset([PJ.PROCESSING])),
        rules.ChildrenAny(R.PROJECT_LIBRARIES, SEQUENCED_LIBRARY),
        rules.ChildrenNone(R.PROJECT_LIBRARIES, OPEN_LIBRARY),
    ),
    reason="project has sequenced libraries and none with open work", where=_SU,
)

REQUEST_FINISHED = operation(
    "worker.request_finished", "Request finished", K.WORKER, E.SEQ_REQUEST,
    effect(E.SEQ_REQUEST, RQ.DATA_PROCESSING, RQ.FINISHED),
    guard=rules.StatusIn(frozenset([RQ.DATA_PROCESSING])) & rules.ChildrenAll(R.REQUEST_LIBRARIES, at_least(LB.SHARED)),
    reason="no library of the request is below SHARED", where=_SU,
)

ALL = collect(globals())
ORDER = (
    EXPERIMENT_SEQUENCING, EXPERIMENT_RUN_FINISHED, LIBRARY_SEQUENCED, SAMPLE_STORED, POOL_SEQUENCED,
    REQUEST_REOPEN, REQUEST_SAMPLES_RECEIVED, REQUEST_PREPARED, REQUEST_DATA_PROCESSING,
    PROJECT_REOPEN, PROJECT_SEQUENCED, REQUEST_FINISHED,
)
