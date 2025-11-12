from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False)
class MUXTypeEnum(DBEnum):
    abbreviation: str
    mux_columns: list[str]

    @property
    def select_name(self) -> str:
        return str(self.id)


class MUXType(ExtendedEnum[MUXTypeEnum], enum_type=MUXTypeEnum):
    CUSTOM = MUXTypeEnum(0, "Custom", "Custom", ["barcode"])
    TENX_OLIGO = MUXTypeEnum(1, "10X Oligo-based Cell Tagging (CMO/HTO/LMO..) Multiplexing", "Oligo", ["barcode", "read", "pattern"])
    TENX_ON_CHIP = MUXTypeEnum(2, "10X On-Chip Multiplexing", "OCM", ["barcode"])
    TENX_FLEX_PROBE = MUXTypeEnum(3, "10X Flex Probe Multiplexing", "Flex", ["barcode"])
    TENX_ABC_HASH = MUXTypeEnum(4, "10X Antibody-based Cell Hashing Multiplexing", "ABC", ["barcode", "read", "pattern"])
    PARSE_WELLS = MUXTypeEnum(5, "Parse Biosciences Well-based Multiplexing", "Parse", ["barcode"])
