from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class LibraryStatusEnum(DBEnum):
    icon: str


class LibraryStatus(ExtendedEnum[LibraryStatusEnum], enum_type=LibraryStatusEnum):
    DRAFT = LibraryStatusEnum(0, "Draft", "✍🏼")
    SUBMITTED = LibraryStatusEnum(1, "Submitted", "🚀")
    POOLED = LibraryStatusEnum(2, "Pooled", "🧪")
    SEQUENCED = LibraryStatusEnum(3, "Sequenced", "🧬")
    SHARED = LibraryStatusEnum(4, "Shared", "📬")
    FAILED = LibraryStatusEnum(10, "Failed", "❌")