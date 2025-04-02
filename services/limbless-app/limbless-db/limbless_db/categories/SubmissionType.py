from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class SubmissionTypeEnum(DBEnum):
    description: str


class SubmissionType(ExtendedEnum[SubmissionTypeEnum], enum_type=SubmissionTypeEnum):
    RAW_SAMPLES = SubmissionTypeEnum(1, "Raw Samples", "Submit raw samples for library preparation and sequencing.")
    POOLED_LIBRARIES = SubmissionTypeEnum(2, "Pooled Libraries", "Submit ready-to-sequence pooled libraries for sequencing.")
    UNPOOLED_LIBRARIES = SubmissionTypeEnum(3, "Un-Pooled Libraries", "Submit un-pooled libraries for pooling and sequencing.")