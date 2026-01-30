from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False, frozen=True)
class BarcodeOrientationEnum(DBEnum):
    label: str
    description: str
    validated: bool


class BarcodeOrientation(ExtendedEnum):
    label: str
    description: str
    validated: bool

    FORWARD = BarcodeOrientationEnum(1, "Forward (Validated)", "3' -> 5'", True)
    REVERSE_COMPLEMENT = BarcodeOrientationEnum(2, "Reverse Complement (Validated)", "3' -> 5'", True)
    FORWARD_NOT_VALIDATED = BarcodeOrientationEnum(3, "Forward (Not Validated)", "3' -> 5'", False)
    REVERSE_COMPLEMENT_NOT_VALIDATED = BarcodeOrientationEnum(4, "Reverse Complement (Not Validated)", "3' -> 5'", False)
