from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum
from .BarcodeType import BarcodeTypeEnum, BarcodeType


@dataclass(eq=False)
class BarcodeOrientationEnum(DBEnum):
    description: str


class BarcodeOrientation(ExtendedEnum[BarcodeOrientationEnum], enum_type=BarcodeOrientationEnum):
    FORWARD = BarcodeOrientationEnum(1, "Forward", "3' -> 5'")
    REVERSE_COMPLEMENT = BarcodeOrientationEnum(2, "Reverse Complement", "5' -> 3'")
