from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False)
class MUXTypeEnum(DBEnum):
    abbreviation: str

    @property
    def select_name(self) -> str:
        return str(self.id)


class MUXType(ExtendedEnum[MUXTypeEnum], enum_type=MUXTypeEnum):
    CUSTOM = MUXTypeEnum(0, "Custom", "Custom")
    TENX_OLIGO = MUXTypeEnum(1, "10X Oligo-based Cell Tagging (CMO/HTO/LMO..) Multiplexing", "Oligo")
    TENX_ON_CHIP = MUXTypeEnum(2, "10X On-Chip Multiplexing", "OCM")
    TENX_FLEX_PROBE = MUXTypeEnum(3, "10X Flex Probe Multiplexing", "Flex")
