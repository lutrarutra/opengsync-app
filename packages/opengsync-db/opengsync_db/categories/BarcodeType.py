from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False, frozen=True)
class BarcodeTypeEnum(DBEnum):
    label: str
    variable: str
    abbreviation: str


class BarcodeType(ExtendedEnum):
    label: str
    variable: str
    abbreviation: str

    INDEX_I7 = BarcodeTypeEnum(1, "Index i7", "index_i7", "i7")
    INDEX_I5 = BarcodeTypeEnum(2, "Index i5", "index_i5", "i5")