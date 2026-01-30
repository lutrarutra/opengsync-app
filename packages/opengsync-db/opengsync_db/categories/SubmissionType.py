from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False, frozen=True)
class SubmissionTypeEnum(DBEnum):
    label: str
    abbreviation: str
    description: str


class SubmissionType(ExtendedEnum):
    label: str
    abbreviation: str
    description: str
    
    RAW_SAMPLES = SubmissionTypeEnum(1, "Raw Samples", "Raw", "Submit raw samples for library preparation and sequencing.")
    POOLED_LIBRARIES = SubmissionTypeEnum(2, "Pooled Libraries", "Pooled", "Submit ready-to-sequence pooled libraries for sequencing.")
    UNPOOLED_LIBRARIES = SubmissionTypeEnum(3, "Un-Pooled Libraries", "Un-Pooled", "Submit un-pooled libraries for pooling and sequencing.")

    @classmethod
    def as_selectable(cls, inlcude_unpooled_libraries: bool = True) -> list[tuple[int, str]]:
        return [(item.id, item.name) for item in cls.as_list() if item != cls.UNPOOLED_LIBRARIES and not inlcude_unpooled_libraries]