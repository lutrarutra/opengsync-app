"""Migrations and changes made outside any operation."""
from ._common import *  # noqa: F401,F403
from ._common import collect

BASELINE = operation(
    "migration.baseline", "Status at migration", K.MIGRATION, None,
    *(effect(entity, NEW, ANY) for entity in E.ENTITIES),
    reason="status at the time status history was introduced",
    doc="One change per existing record. History before this point is unknown.",
)

INFERRED = operation(
    "migration.inferred", "Inferred from timestamps", K.MIGRATION, None,
    *(effect(entity, NEW, ANY) for entity in E.ENTITIES),
    reason="inferred from existing timestamp columns",
    doc="Changes reconstructed from timestamp columns (submitted, stored, created, run started/completed); marked inferred.",
)

RESTORE_PREPARING = operation(
    "migration.restore_preparing", "Restore PREPARING", K.MIGRATION, None,
    effect(E.LIBRARY, below(LB.PREPARING), LB.PREPARING),
    reason="restore PREPARING lost in d9685235 (2026-06-10): library is in a lab prep",
    where=["services/db/alembic/versions/d5a7c3e9f142_restore_library_preparing.py"],
    doc="Libraries added to a lab prep between 2026-06-10 and the fix stayed ACCEPTED.",
)

UNATTRIBUTED = operation(
    "system.unattributed", "Unattributed change", K.SYSTEM, None,
    reason="no operation context at {location}",
    doc="A status changed outside `run_operation`. The reason names the code location that needs wrapping.",
)

ALL = collect(globals())
