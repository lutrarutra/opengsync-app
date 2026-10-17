from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False, frozen=True)
class ChecklistTypeEnum(DBEnum):
    label: str


class ChecklistType(ExtendedEnum):
    """Checklist whose steps are checked by hand; see `ChecklistLog`."""
    label: str

    SEQ_REQUEST_REVIEW = ChecklistTypeEnum(1, label="Request Review")
    EXPERIMENT = ChecklistTypeEnum(2, label="Experiment")
