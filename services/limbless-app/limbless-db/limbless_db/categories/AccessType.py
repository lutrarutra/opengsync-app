from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class AccessTypeEnum(DBEnum):
    icon: str
    
    @property
    def select_name(self) -> str:
        return self.icon


class AccessType(ExtendedEnum[AccessTypeEnum], enum_type=AccessTypeEnum):
    ADMIN = AccessTypeEnum(1, "Admin", "🤓")
    VIEW = AccessTypeEnum(2, "View", "👀")
    EDIT = AccessTypeEnum(3, "Edit", "📝")
