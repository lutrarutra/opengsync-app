from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class AffiliationTypeEnum(DBEnum):
    icon: str
    
    @property
    def select_name(self) -> str:
        return self.icon


class AffiliationType(ExtendedEnum[AffiliationTypeEnum], enum_type=AffiliationTypeEnum):
    MANAGER = AffiliationTypeEnum(1, "Manager", "🤓")
    MEMBER = AffiliationTypeEnum(2, "Member", "👨🏾‍💻")
