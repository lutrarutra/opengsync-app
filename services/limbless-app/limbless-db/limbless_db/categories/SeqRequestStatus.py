from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class SeqRequestStatusEnum(DBEnum):
    icon: str


class SeqRequestStatus(ExtendedEnum[SeqRequestStatusEnum], enum_type=SeqRequestStatusEnum):
    DRAFT = SeqRequestStatusEnum(0, "Draft", "✍🏼")
    SUBMITTED = SeqRequestStatusEnum(1, "Submitted", "🚀")
    PREPARATION = SeqRequestStatusEnum(2, "Sequencing Preparation", "🧬")
    DATA_PROCESSING = SeqRequestStatusEnum(3, "Data Processing", "👨🏽‍💻")
    FINISHED = SeqRequestStatusEnum(4, "Finished", "✅")
    ARCHIVED = SeqRequestStatusEnum(5, "Archived", "🗃️")
    FAILED = SeqRequestStatusEnum(6, "Failed", "❌")