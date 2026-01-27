from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False)
class LibraryStatusEnum(DBEnum):
    icon: str
    description: str

    @property
    def select_name(self) -> str:
        return self.icon

    @property
    def display_name(self) -> str:
        return f"{self.name} {self.icon}"
    

class LibraryStatus(ExtendedEnum[LibraryStatusEnum], enum_type=LibraryStatusEnum):
    DRAFT = LibraryStatusEnum(0, "Draft", "✍🏼", "Draft plan of the library")
    SUBMITTED = LibraryStatusEnum(1, "Submitted", "🚀", "Submitted plan with sequencing request for review")
    ACCEPTED = LibraryStatusEnum(2, "Accepted", "👍", "Library plan was accepted for sequencing")
    PREPARING = LibraryStatusEnum(3, "Preparing", "🔬", "Library is being prepared for sequencing")
    STORED = LibraryStatusEnum(4, "Stored", "📦", "Library is received and stored")
    POOLED = LibraryStatusEnum(5, "Pooled", "🧪", "Library is prepared and pooled and ready for sequencing")
    SEQUENCED = LibraryStatusEnum(6, "Sequenced", "✅", "Sequencing is finished")
    SHARED = LibraryStatusEnum(7, "Shared", "📤", "Sequencing data is shared with the customer(s)")
    FAILED = LibraryStatusEnum(10, "Failed", "❌", "Sequencing of the library could not be completed")
    REJECTED = LibraryStatusEnum(11, "Rejected", "⛔", "Library was not accepted to be sequenced by staff")
    ARCHIVED = LibraryStatusEnum(12, "Archived", "🗃️", "Library is sequenced and the data is archived")
    REMOVED = LibraryStatusEnum(13, "Removed", "🗑️", "Library was removed")