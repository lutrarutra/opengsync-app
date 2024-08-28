from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class AffiliationTypeEnum(DBEnum):
    icon: str
    
    @property
    def select_name(self) -> str:
        return self.icon


class AffiliationType(ExtendedEnum[AffiliationTypeEnum], enum_type=AffiliationTypeEnum):
    OWNER = AffiliationTypeEnum(1, "Owner", "👑")
    MANAGER = AffiliationTypeEnum(2, "Manager", "🤓")
    MEMBER = AffiliationTypeEnum(3, "Member", "👨🏾‍💻")
