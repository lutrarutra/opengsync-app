from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False, frozen=True)
class PrepStatusEnum(DBEnum):
    label: str
    icon: str


class PrepStatus(ExtendedEnum):
    label: str
    icon: str

    PREPARING = PrepStatusEnum(0, "Preparing", "🧪")
    COMPLETED = PrepStatusEnum(1, "Completed", "✅")
    ARCHIVED = PrepStatusEnum(10, "Archived", "🗃️")

    
    @property
    def select_name(self) -> str:
        return self.icon
