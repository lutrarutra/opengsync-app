from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class AssayTypeEnum(DBEnum):
    abbreviation: str


class AssayType(ExtendedEnum[AssayTypeEnum], enum_type=AssayTypeEnum):
    CUSTOM = AssayTypeEnum(0, "Custom", "CUSTOM")
    RNA = AssayTypeEnum(1, "RNA", "RNA")
    VISIUM = AssayTypeEnum(2, "Visium", "VISIUM")
    ATAC = AssayTypeEnum(3, "ATAC", "ATAC")