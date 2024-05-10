from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class LibraryStatusEnum(DBEnum):
    icon: str

    @property
    def select_name(self) -> str:
        return self.icon


class LibraryStatus(ExtendedEnum[LibraryStatusEnum], enum_type=LibraryStatusEnum):
    DRAFT = LibraryStatusEnum(0, "Draft", "✍🏼")
    SUBMITTED = LibraryStatusEnum(1, "Submitted", "🚀")
    ACCEPTED = LibraryStatusEnum(2, "Accepted", "📦")
    POOLED = LibraryStatusEnum(3, "Pooled", "🧪")
    SEQUENCED = LibraryStatusEnum(4, "Sequenced", "🧬")
    SHARED = LibraryStatusEnum(5, "Shared", "📬")
    FAILED = LibraryStatusEnum(10, "Failed", "❌")
    REJECTED = LibraryStatusEnum(11, "Rejected", "⛔")