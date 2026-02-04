from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False, frozen=True)
class GroupTypeEnum(DBEnum):
    label: str
    icon: str

class GroupType(ExtendedEnum):
    label: str
    icon: str
    
    INSTITUTION = GroupTypeEnum(1, "Institution", "🏛️")
    RESEARCH_GROUP = GroupTypeEnum(2, "Research Group/Lab", "👥")
    COLLABORATION = GroupTypeEnum(3, "Collaboration", "🌍")

    @property
    def select_name(self) -> str:
        return self.icon
    
    @property
    def display_name(self) -> str:
        return f"{self.label} {self.icon}"

