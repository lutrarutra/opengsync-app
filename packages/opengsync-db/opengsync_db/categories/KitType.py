from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False, frozen=True)
class KitTypeEnum(DBEnum):
    pass


class KitType(ExtendedEnum):
    INDEX_KIT = KitTypeEnum(1)
    FEATURE_KIT = KitTypeEnum(2)
    LIBRARY_KIT = KitTypeEnum(3)
