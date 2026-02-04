from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False, frozen=True)
class AffiliationTypeEnum(DBEnum):
    label: str
    icon: str
    

class AffiliationType(ExtendedEnum):
    label: str
    icon: str
    
    OWNER = AffiliationTypeEnum(1, "Owner", "👑")
    MANAGER = AffiliationTypeEnum(2, "Manager", "🤓")
    MEMBER = AffiliationTypeEnum(3, "Member", "👨🏾‍💻")

    @classmethod
    def as_selectable_no_owner(cls) -> list[tuple[int, str]]:
        return [(e.id, e.display_name) for e in AffiliationType.as_list() if e != AffiliationType.OWNER]  # type: ignore

    @property
    def select_name(self) -> str:
        return self.icon

    @property
    def display_name(self) -> str:
        return f"{self.label} {self.icon}"