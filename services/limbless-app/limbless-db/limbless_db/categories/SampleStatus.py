from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class SampleStatusEnum(DBEnum):
    icon: str
    description: str

    @property
    def select_name(self) -> str:
        return self.icon


class SampleStatus(ExtendedEnum[SampleStatusEnum], enum_type=SampleStatusEnum):
    DRAFT = SampleStatusEnum(0, "Draft", "✍🏼", "Draft plan of the sample")
    SUBMITTED = SampleStatusEnum(1, "Submitted", "🚀", "Submitted plan with sequencing request for review")
    ACCEPTED = SampleStatusEnum(2, "Accepted", "✅", "Sample plan was accepted for sequencing")
    STORED = SampleStatusEnum(3, "Stored", "📦", "Library is received and stored")
    PREPARED = SampleStatusEnum(4, "Prepared", "🧪", "All libraries of the sample are prepared and ready for sequencing")
    SEQUENCED = SampleStatusEnum(5, "Sequenced", "🧬", "All libraries of the sample are sequenced")
    SHARED = SampleStatusEnum(6, "Shared", "📬", "Data from the library is shared")
    FAILED = SampleStatusEnum(10, "Failed", "❌", "Sequencing of the library could not be completed")
    REJECTED = SampleStatusEnum(11, "Rejected", "⛔", "Library was not accepted to be sequenced by staff")
    ARCHIVED = SampleStatusEnum(12, "Archived", "🗃️", "Library is sequenced and the data is archived")