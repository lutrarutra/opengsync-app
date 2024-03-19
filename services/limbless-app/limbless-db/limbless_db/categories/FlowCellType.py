from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class FlowCellTypeEnum(DBEnum):
    manufacturer: str
    num_lanes: int
    max_m_reads_per_lane: int


# https://emea.illumina.com/systems/sequencing-platforms/novaseq/specifications.html
class FlowCellType(ExtendedEnum[FlowCellTypeEnum], enum_type=FlowCellTypeEnum):
    SP_ILLUMINA = FlowCellTypeEnum(1, "SP", "Illumina", 2, 650)
    S1_ILLUMINA = FlowCellTypeEnum(2, "S1", "Illumina", 2, 1300)
    S2_ILLUMINA = FlowCellTypeEnum(3, "S2", "Illumina", 2, 3300)
    S4_ILLUMINA = FlowCellTypeEnum(4, "S4", "Illumina", 4, 8000)
