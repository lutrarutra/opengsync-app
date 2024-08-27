from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class GroupTypeEnum(DBEnum):
    icon: str
    
    @property
    def select_name(self) -> str:
        return self.icon


class GroupType(ExtendedEnum[GroupTypeEnum], enum_type=GroupTypeEnum):
    INSTITUTION = GroupTypeEnum(1, "Institution", "🏛️")
    RESEARCH_GROUP = GroupTypeEnum(2, "Research Group/Lab", "👥")
    COLLABORATION = GroupTypeEnum(3, "Collaboration", "🌍")
