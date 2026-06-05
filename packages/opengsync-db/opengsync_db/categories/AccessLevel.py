from dataclasses import dataclass
from .ExtendedEnum import DBEnum, ExtendedEnum

@dataclass(eq=False, frozen=True)
class AccessLevelEnum(DBEnum):
    label: str
    icon: str


class AccessLevel(ExtendedEnum):
    label: str
    icon: str
    
    ADMIN = AccessLevelEnum(100, "Admin", "🤓")
    INSIDER = AccessLevelEnum(90, "Insider", "👥")
    OWNER = AccessLevelEnum(50, "Owner", "👑")
    WRITE = AccessLevelEnum(20, "Write", "📝")
    READ = AccessLevelEnum(10, "Read", "👀")
    NONE = AccessLevelEnum(0, "None", "🚫")

    @property
    def select_name(self) -> str:
        return self.icon