"""The nine status-bearing entities."""
from ..categories import (
    SeqRequestStatus, ProjectStatus, SampleStatus, LibraryStatus, PoolStatus, PrepStatus,
    ExperimentStatus, RunStatus, DeliveryStatus,
)
from .core import Entity

SEQ_REQUEST = Entity(
    "seq_request", "Request", "SeqRequest", SeqRequestStatus, plural="Requests",
    unused=((SeqRequestStatus.FAILED, "never set anywhere"),),
)
PROJECT = Entity("project", "Project", "Project", ProjectStatus)
SAMPLE = Entity(
    "sample", "Sample", "Sample", SampleStatus, nullable=True,
    manual_only=frozenset([SampleStatus.DEPLETED]),
)
LIBRARY = Entity(
    "library", "Library", "Library", LibraryStatus, plural="Libraries",
    manual_only=frozenset([LibraryStatus.ARCHIVED, LibraryStatus.REMOVED, LibraryStatus.QC_COMPLETED]),
)
POOL = Entity(
    "pool", "Pool", "Pool", PoolStatus,
    manual_only=frozenset([PoolStatus.ARCHIVED]),
)
LAB_PREP = Entity(
    "lab_prep", "Lab prep", "LabPrep", PrepStatus,
    unused=((PrepStatus.ARCHIVED, "never set anywhere"),),
)
EXPERIMENT = Entity(
    "experiment", "Experiment", "Experiment", ExperimentStatus,
    manual_only=frozenset([ExperimentStatus.DRAFT, ExperimentStatus.FAILED, ExperimentStatus.CANCELED]),
)
SEQ_RUN = Entity(
    "seq_run", "Seq run", "SeqRun", RunStatus,
    manual_only=frozenset([RunStatus.IDLE, RunStatus.FAILED]),
)
DELIVERY_LINK = Entity(
    "seq_request_delivery_email_link", "Delivery email", "links.SeqRequestDeliveryEmailLink", DeliveryStatus,
    id_attr="seq_request_id", key_attr="email",
)

ENTITIES: tuple[Entity, ...] = (
    SEQ_REQUEST, PROJECT, SAMPLE, LIBRARY, POOL, LAB_PREP, EXPERIMENT, SEQ_RUN, DELIVERY_LINK,
)
BY_NAME: dict[str, Entity] = {e.name: e for e in ENTITIES}
