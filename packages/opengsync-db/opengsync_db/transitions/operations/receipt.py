"""Receipt of samples, libraries and pools."""
from ._common import *  # noqa: F401,F403
from ._common import collect

STORE_SAMPLES = operation(
    "receipt.store_samples", "Store samples", K.ACTION, E.SEQ_REQUEST,
    effect(E.SAMPLE, ANY, SA.STORED, via="samples", when="selected"),
    effect(E.LIBRARY, ANY, [LB.POOLED, LB.STORED], via="libraries", when="selected; POOLED if in a pool"),
    effect(E.POOL, ANY, PL.STORED, via="pools", when="selected"),
    effect(E.SEQ_REQUEST, ANY, RQ.SAMPLES_RECEIVED, when="raw samples: all samples ≥ STORED; un-pooled / QC only: all libraries ≥ STORED"),
    effect(E.SEQ_REQUEST, ANY, RQ.PREPARED, when="pooled libraries: all pools ≥ STORED"),
    effect(E.LIBRARY, at_least(LB.STORED), LB.QC_PENDING, via="libraries", when="QC only: all libraries ≥ STORED"),
    guard=rules.StatusIn(frozenset([RQ.ACCEPTED])),
    where=[B + "forms/actions/StoreSamplesAction.py"],
    gap="selected samples, libraries and pools are not checked for their status, and the request status is not checked",
)

ALL = collect(globals())
