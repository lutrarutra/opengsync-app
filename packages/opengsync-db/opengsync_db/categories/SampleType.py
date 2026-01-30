from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False, frozen=True)
class SampleTypeEnum(DBEnum):
    label: str


# https://emea.illumina.com/systems/sequencing-platforms/novaseq/specifications.html
class SampleType(ExtendedEnum):
    label: str
    CUSTOM = SampleTypeEnum(0, "Custom")
    CELL_SUSPENSION = SampleTypeEnum(1, "Cell Suspension")
    FRESH_TISSUE = SampleTypeEnum(2, "Fresh Tissue")
    FROZEN_TISSUE = SampleTypeEnum(3, "Frozen Tissue")
    FFPE = SampleTypeEnum(4, "FFPE Tissue")
