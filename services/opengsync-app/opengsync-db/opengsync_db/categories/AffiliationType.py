from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False)
class AffiliationTypeEnum(DBEnum):
    icon: str
    
    @property
    def select_name(self) -> str:
        return self.icon

    @property
    def display_name(self) -> str:
        return f"{self.name} {self.icon}"
    

class AffiliationType(ExtendedEnum[AffiliationTypeEnum], enum_type=AffiliationTypeEnum):
    OWNER = AffiliationTypeEnum(1, "Owner", "👑")
    MANAGER = AffiliationTypeEnum(2, "Manager", "🤓")
    MEMBER = AffiliationTypeEnum(3, "Member", "👨🏾‍💻")

    @classmethod
    def as_selectable_no_owner(cls) -> list[tuple[int, str]]:
        return [(e.id, e.display_name) for e in AffiliationType.as_list() if e != AffiliationType.OWNER]  # type: ignore
