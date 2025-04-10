from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False)
class PrepStatusEnum(DBEnum):
    icon: str

    @property
    def select_name(self) -> str:
        return self.icon


class PrepStatus(ExtendedEnum[PrepStatusEnum], enum_type=PrepStatusEnum):
    PREPARING = PrepStatusEnum(0, "Preparing", "🧪")
    COMPLETED = PrepStatusEnum(1, "Completed", "✅")
    ARCHIVED = PrepStatusEnum(10, "Archived", "🗃️")