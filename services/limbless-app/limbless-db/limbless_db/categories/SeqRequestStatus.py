from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class SeqRequestStatusEnum(DBEnum):
    icon: str

    @property
    def select_name(self) -> str:
        return self.icon


class SeqRequestStatus(ExtendedEnum[SeqRequestStatusEnum], enum_type=SeqRequestStatusEnum):
    DRAFT = SeqRequestStatusEnum(0, "Draft", "✍🏼")
    SUBMITTED = SeqRequestStatusEnum(1, "Submitted", "🚀")
    ACCEPTED = SeqRequestStatusEnum(2, "Accepted", "👍🏼")
    SAMPLES_RECEIVED = SeqRequestStatusEnum(3, "Samples Received", "📬")
    PREPARED = SeqRequestStatusEnum(4, "Prepared", "🧪")
    DATA_PROCESSING = SeqRequestStatusEnum(5, "Data Processing", "👨🏽‍💻")
    FINISHED = SeqRequestStatusEnum(6, "Finished", "✅")
    FAILED = SeqRequestStatusEnum(10, "Failed", "❌")
    REJECTED = SeqRequestStatusEnum(11, "Rejected", "⛔")
    ARCHIVED = SeqRequestStatusEnum(12, "Archived", "🗃️")