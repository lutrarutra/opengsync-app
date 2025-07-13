from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False)
class BarcodeTypeEnum(DBEnum):
    variable: str
    abbreviation: str


class BarcodeType(ExtendedEnum[BarcodeTypeEnum], enum_type=BarcodeTypeEnum):
    INDEX_I7 = BarcodeTypeEnum(1, "Index i7", "index_i7", "i7")
    INDEX_I5 = BarcodeTypeEnum(2, "Index i5", "index_i5", "i5")