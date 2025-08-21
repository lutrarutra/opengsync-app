from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False)
class AccessTypeEnum(DBEnum):
    icon: str
    
    @property
    def select_name(self) -> str:
        return self.icon


class AccessType(ExtendedEnum[AccessTypeEnum], enum_type=AccessTypeEnum):
    ADMIN = AccessTypeEnum(100, "Admin", "🤓")
    INSIDER = AccessTypeEnum(90, "Insider", "👥")
    OWNER = AccessTypeEnum(50, "Owner", "👑")
    EDIT = AccessTypeEnum(20, "Edit", "📝")
    VIEW = AccessTypeEnum(10, "View", "👀")
    NONE = AccessTypeEnum(0, "None", "🚫")
