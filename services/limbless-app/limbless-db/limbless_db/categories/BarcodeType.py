from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class BarcodeTypeEnum(DBEnum):
    variable: str


class BarcodeType(ExtendedEnum[BarcodeTypeEnum], enum_type=BarcodeTypeEnum):
    INDEX_1 = BarcodeTypeEnum(1, "Index 1", "index_1")
    INDEX_2 = BarcodeTypeEnum(2, "Index 2", "index_2")
    INDEX_3 = BarcodeTypeEnum(3, "Index 3", "index_3")
    INDEX_4 = BarcodeTypeEnum(4, "Index 4", "index_4")