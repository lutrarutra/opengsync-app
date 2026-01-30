from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False, frozen=True)
class KitTypeEnum(DBEnum):
    label: str


class KitType(ExtendedEnum):
    label: str
    INDEX_KIT = KitTypeEnum(1, "Index Kit")
    FEATURE_KIT = KitTypeEnum(2, "Feature Kit")
    LIBRARY_KIT = KitTypeEnum(3, "Library Kit")
