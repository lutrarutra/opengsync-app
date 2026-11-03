from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False, frozen=True)
class SubmissionLayoutTypeEnum(DBEnum):
    label: str
    icon: str
    description: str


class SubmissionLayoutType(ExtendedEnum):
    label: str
    icon: str
    description: str

    TUBES = SubmissionLayoutTypeEnum(1, "Tubes", "bi-prescription2", "Each item is in its own labelled tube.")
    PLATE = SubmissionLayoutTypeEnum(2, "96-Well Plate", "bi-grid-3x3", "Items are in the wells (A1-H12) of one or more 96-well plates.")
