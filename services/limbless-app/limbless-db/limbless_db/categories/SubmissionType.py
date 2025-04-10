from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False)
class SubmissionTypeEnum(DBEnum):
    description: str


class SubmissionType(ExtendedEnum[SubmissionTypeEnum], enum_type=SubmissionTypeEnum):
    RAW_SAMPLES = SubmissionTypeEnum(1, "Raw Samples", "Submit raw samples for library preparation and sequencing.")
    POOLED_LIBRARIES = SubmissionTypeEnum(2, "Pooled Libraries", "Submit ready-to-sequence pooled libraries for sequencing.")
    UNPOOLED_LIBRARIES = SubmissionTypeEnum(3, "Un-Pooled Libraries", "Submit un-pooled libraries for pooling and sequencing.")

    @classmethod
    def as_selectable(cls, inlcude_unpooled_libraries: bool = True) -> list[tuple[int, str]]:
        return [(item.id, item.name) for item in cls.as_list() if item != cls.UNPOOLED_LIBRARIES and not inlcude_unpooled_libraries]