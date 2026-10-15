"""Library prep, pooling, pool handling and QC measurements."""
from ._common import *  # noqa: F401,F403
from ._common import collect

_PREPARING = rules.StatusIn(frozenset([PR.PREPARING]))

ADD_LIBRARIES = operation(
    "prep.add_libraries", "Add libraries to lab prep", K.ACTION, E.LAB_PREP,
    effect(E.LIBRARY, below(LB.PREPARING), LB.PREPARING, via="libraries"),
    guard=_PREPARING,
    where=[B + "forms/actions/LibraryPrepAction.py", DB + "core/actions.py:add_libraries_to_prep"],
)

REMOVE_LIBRARY = operation(
    "prep.remove_library", "Remove library from lab prep", K.ACTION, E.LAB_PREP,
    effect(E.LIBRARY, LB.PREPARING, LB.ACCEPTED, via="libraries"),
    guard=_PREPARING,
    where=[B + "routes/htmx/lab_preps.py:remove_library_from_prep", DB + "core/actions.py:remove_library_from_prep"],
)

UPLOAD_TABLE = operation(
    "prep.upload_table", "Upload library prep table", K.ACTION, E.LAB_PREP,
    effect(E.LIBRARY, ANY, LB.FAILED, via="libraries", when="pool column is 'x'"),
    where=[B + "forms/actions/UploadLibraryPrepSpreadsheetAction.py"],
)

REJECT_SAMPLES = operation(
    "prep.reject_samples", "Reject samples", K.ACTION, E.LAB_PREP,
    effect(E.SAMPLE, frozenset(SA) - {SA.REJECTED}, SA.REJECTED, via="libraries.sample_links.sample", when="row marked 'x'"),
    effect(E.SAMPLE, SA.REJECTED, SA.STORED, via="libraries.sample_links.sample", when="mark removed"),
    where=[B + "forms/actions/RejectSamplesAction.py"],
)

POOL_LIBRARIES = operation(
    "prep.pool_libraries", "Pool libraries", K.WORKFLOW, E.LAB_PREP,
    effect(E.POOL, NEW, PL.DRAFT, via="pools", when="existing pools of the prep are deleted and recreated"),
    effect(E.LIBRARY, ANY, LB.FAILED, via="libraries", when="pool is 'x'"),
    effect(E.LIBRARY, ANY, LB.POOLED, via="libraries"),
    effect(E.SEQ_REQUEST, RQ.ACCEPTED, RQ.PREPARED, via="libraries.seq_request", when="all libraries of the request ≥ POOLED"),
    guard=_PREPARING,
    where=[B + "forms/workflows/library_pooling/CompleteLibraryPoolingForm.py"],
)

COMPLETE = operation(
    "prep.complete", "Complete lab prep", K.ACTION, E.LAB_PREP,
    effect(E.POOL, below(PL.STORED), PL.STORED, via="pools"),
    effect(E.SEQ_REQUEST, ANY, RQ.PREPARED, via="libraries.seq_request", when="all libraries of the request ≥ POOLED",
           gap="no status check: can move DATA_PROCESSING, FINISHED or ARCHIVED requests back"),
    effect(E.LAB_PREP, ANY, PR.COMPLETED),
    guard=_PREPARING,
    where=[B + "routes/htmx/lab_preps.py:complete_lab_prep"],
)

UNCOMPLETE = operation(
    "prep.uncomplete", "Reopen lab prep", K.ACTION, E.LAB_PREP,
    effect(E.LAB_PREP, ANY, PR.PREPARING),
    guard=rules.StatusIn(frozenset([PR.COMPLETED])),
    where=[B + "routes/htmx/lab_preps.py:uncomplete_lab_prep"],
)

MERGE_POOLS = operation(
    "pool.merge", "Merge pools", K.WORKFLOW, E.POOL,
    effect(E.POOL, NEW, ANY, when="chosen status; prefilled with the shared status of the source pools"),
    effect(E.POOL, ANY, PL.REPOOLED, when="source pools"),
    where=[B + "forms/workflows/merge_pools/MergePoolsForm.py", DB + "core/actions.py:merge_pools"],
    doc="Non-staff merges create a DRAFT pool.",
)

REMOVE_POOL_LIBRARY = operation(
    "pool.remove_libraries", "Remove libraries from pool", K.ACTION, E.POOL,
    effect(E.LIBRARY, LB.POOLED, LB.STORED, via="libraries"),
    guard=rules.StatusIn(frozenset([PL.DRAFT])),
    where=[B + "routes/htmx/pools.py:remove_library_from_pool", B + "routes/htmx/pools.py:remove_libraries_from_pool"],
)

QUBIT = operation(
    "qc.qubit", "Qubit measurement", K.WORKFLOW, None,
    effect(E.POOL, PL.ACCEPTED, PL.STORED, when="pool was measured"),
    where=[B + "forms/workflows/qubit_measure/QubitMeasureForm.py"],
)

BA_REPORT = operation(
    "qc.ba_report", "Bioanalyzer report", K.WORKFLOW, None,
    effect(E.POOL, PL.ACCEPTED, PL.STORED, when="fragment size entered"),
    where=[B + "forms/workflows/ba_report/CompleteBAReport.py"],
)

ALL = collect(globals())
