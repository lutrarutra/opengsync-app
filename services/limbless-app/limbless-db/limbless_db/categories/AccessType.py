from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False)
class AccessTypeEnum(DBEnum):
    icon: str
    
    @property
    def select_name(self) -> str:
        return self.icon


class AccessType(ExtendedEnum[AccessTypeEnum], enum_type=AccessTypeEnum):
    ADMIN = AccessTypeEnum(1, "Admin", "🤓")
    OWNER = AccessTypeEnum(2, "Owner", "👑")
    VIEW = AccessTypeEnum(3, "View", "👀")
    EDIT = AccessTypeEnum(4, "Edit", "📝")
