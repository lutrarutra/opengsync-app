from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False)
class SeqRequestStatusEnum(DBEnum):
    icon: str
    description: str

    @property
    def select_name(self) -> str:
        return self.icon
    
    @property
    def display_name(self) -> str:
        return f"{self.name} {self.icon}"


class SeqRequestStatus(ExtendedEnum[SeqRequestStatusEnum], enum_type=SeqRequestStatusEnum):
    DRAFT = SeqRequestStatusEnum(0, "Draft", "✍🏼", "Request is in its planning stage")
    SUBMITTED = SeqRequestStatusEnum(1, "Submitted", "🚀", "Request is submitted for validation")
    ACCEPTED = SeqRequestStatusEnum(2, "Accepted", "👍", "Request is accepted and waiting for samples to be delivered")
    SAMPLES_RECEIVED = SeqRequestStatusEnum(3, "Samples Stored", "📦", "All samples are received and stored")
    PREPARED = SeqRequestStatusEnum(4, "Prepared", "🧪", "All libraries are prepared and pooled, ready for sequencing")
    DATA_PROCESSING = SeqRequestStatusEnum(5, "Data Processing", "👨🏽‍💻", "All libraries are sequenced and being processed")
    FINISHED = SeqRequestStatusEnum(6, "Finished", "✅", "Sequencing data is shared with the requestor")
    FAILED = SeqRequestStatusEnum(10, "Failed", "❌", "Request failed")
    REJECTED = SeqRequestStatusEnum(11, "Rejected", "⛔", "Request was rejected")
    ARCHIVED = SeqRequestStatusEnum(12, "Archived", "🗃️", "Request was archived")