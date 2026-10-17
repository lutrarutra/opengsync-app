"""Creating status-bearing records (initial statuses)."""
from ._common import *  # noqa: F401,F403
from ._common import collect

REQUEST_CREATE = operation(
    "request.create", "Create request", K.ACTION, E.SEQ_REQUEST,
    effect(E.SEQ_REQUEST, NEW, RQ.DRAFT),
    where=[B + "forms/models/SeqRequestForm.py"],
)

SAS_COMPLETE = operation(
    "request.complete_sas", "Complete sample annotation sheet", K.WORKFLOW, E.SEQ_REQUEST,
    effect(E.PROJECT, NEW, PJ.DRAFT, via="samples.project", when="a new project is created"),
    effect(E.SAMPLE, NEW, SA.DRAFT, via="samples", when="raw-sample submissions; pooled-library submissions create samples without status"),
    effect(E.LIBRARY, NEW, LB.DRAFT, via="libraries"),
    effect(E.POOL, NEW, PL.DRAFT, via="pools", when="pooled-library submissions"),
    where=[B + "forms/workflows/library_annotation/CompleteSASForm.py"],
)

PROJECT_CREATE = operation(
    "project.create", "Create project", K.ACTION, E.PROJECT,
    effect(E.PROJECT, NEW, ANY, when="chosen status; non-insiders only DRAFT"),
    where=[B + "forms/models/ProjectForm.py"],
)

POOL_CREATE = operation(
    "pool.create", "Create pool", K.ACTION, E.POOL,
    effect(E.POOL, NEW, ANY, when="chosen status; non-insiders only DRAFT"),
    where=[B + "forms/models/PoolForm.py"],
)

POOL_CLONE = operation(
    "pool.clone", "Clone pool", K.ACTION, E.POOL,
    effect(E.POOL, NEW, ANY, when="chosen status, prefilled STORED (insiders)"),
    effect(E.LIBRARY, NEW, LB.POOLED, via="libraries"),
    where=[B + "forms/models/PoolForm.py"],
)

EXPERIMENT_CREATE = operation(
    "experiment.create", "Create experiment", K.ACTION, E.EXPERIMENT,
    effect(E.EXPERIMENT, NEW, ANY, when="chosen status"),
    where=[B + "forms/models/ExperimentForm.py"],
)

LAB_PREP_CREATE = operation(
    "prep.create", "Create lab prep", K.ACTION, E.LAB_PREP,
    effect(E.LAB_PREP, NEW, PR.PREPARING),
    where=[B + "forms/models/LabPrepForm.py"],
)

REQUEST_CLONE = operation(
    "request.clone", "Clone request", K.ACTION, E.SEQ_REQUEST,
    effect(E.SEQ_REQUEST, NEW, RQ.DRAFT),
    effect(E.LIBRARY, NEW, [LB.POOLED, LB.STORED, LB.ACCEPTED], via="libraries", when="POOLED (pooled), STORED (indexed), ACCEPTED (raw)"),
    effect(E.POOL, NEW, PL.STORED, via="pools", when="pooled"),
    where=[B + "routes/htmx/seq_requests.py", DB + "core/actions.py"],
)

LIBRARY_RESEQ = operation(
    "library.reseq", "Re-sequence libraries", K.ACTION, E.LIBRARY,
    effect(E.LIBRARY, NEW, [LB.STORED, LB.ACCEPTED], when="STORED if indexed, else ACCEPTED"),
    where=[B + "forms/actions/ReseqAction.py"],
)

LIBRARY_RESEQ_SINGLE = operation(
    "library.reseq_single", "Re-sequence one library", K.ACTION, E.LIBRARY,
    effect(E.LIBRARY, NEW, LB.PREPARING),
    where=[B + "routes/htmx/seq_requests.py"],
)

MUX_SAMPLE_POOLING = operation(
    "mux.sample_pooling", "Sample multiplexing (mux prep)", K.WORKFLOW, E.LAB_PREP,
    effect(E.LIBRARY, NEW, ANY, via="libraries", when="new multiplexed libraries copy the status of the library they replace"),
    where=[B + "forms/actions/SamplePoolingAction.py"],
)

ADD_SHARE_EMAIL = operation(
    "request.add_share_email", "Add delivery email", K.ACTION, E.SEQ_REQUEST,
    effect(E.DELIVERY_LINK, NEW, DL.PENDING, via="delivery_email_links"),
    where=[B + "forms/actions/AddSeqRequestShareEmailAction.py"],
)

ALL = collect(globals())
