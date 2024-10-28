from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class KitTypeEnum(DBEnum):
    pass


class KitType(ExtendedEnum[KitTypeEnum], enum_type=KitTypeEnum):
    INDEX_KIT = KitTypeEnum(1, "Index Kit")
    FEATURE_KIT = KitTypeEnum(2, "Feature Kit")
    LIBRARY_KIT = KitTypeEnum(3, "Library Kit")
