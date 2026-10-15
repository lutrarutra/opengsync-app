from ...categories import (  # noqa: F401
    OperationKind as K, SeqRequestStatus as RQ, ProjectStatus as PJ, SampleStatus as SA, LibraryStatus as LB,
    PoolStatus as PL, PrepStatus as PR, ExperimentStatus as EX, RunStatus as RN, DeliveryStatus as DL,
    SubmissionType,
)
from ..core import ANY, NEW, effect, operation, below, at_least  # noqa: F401
from .. import entities as E  # noqa: F401
from .. import relations as R  # noqa: F401
from .. import rules  # noqa: F401

B = "services/backend/server/"
DB = "packages/opengsync-db/opengsync_db/"
W = "packages/opengsync-worker/opengsync_worker/"

OPEN_LIBRARY = frozenset([LB.ACCEPTED, LB.PREPARING, LB.STORED, LB.POOLED])
"""Libraries with lab or sequencing work ahead (status worker); DRAFT/SUBMITTED/QC_PENDING are not counted."""
SEQUENCED_LIBRARY = frozenset([LB.SEQUENCED, LB.SHARED, LB.ARCHIVED])
FINISHED_LIBRARY = frozenset([LB.SHARED, LB.FAILED, LB.REJECTED, LB.ARCHIVED])
EXPERIMENT_DONE = frozenset([EX.SEQUENCED, EX.DEMULTIPLEXED, EX.ARCHIVED])


def collect(namespace: dict) -> tuple:
    from ..core import Operation
    return tuple(v for v in namespace.values() if isinstance(v, Operation))
