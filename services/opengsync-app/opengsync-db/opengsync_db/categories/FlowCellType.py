from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False)
class FlowCellTypeEnum(DBEnum):
    manufacturer: str
    num_lanes: int
    max_m_reads_per_lane: int

    @property
    def max_m_reads(self) -> int:
        return self.num_lanes * self.max_m_reads_per_lane


# https://emea.illumina.com/systems/sequencing-platforms/novaseq/specifications.html
class FlowCellType(ExtendedEnum[FlowCellTypeEnum], enum_type=FlowCellTypeEnum):
    NOVSASEQ_6K_SP = FlowCellTypeEnum(1, "NovaSeq 6000 SP", "Illumina", 2, 325)
    NOVSASEQ_6K_S1 = FlowCellTypeEnum(2, "NovaSeq 6000 S1", "Illumina", 2, 650)
    NOVSASEQ_6K_S2 = FlowCellTypeEnum(3, "NovaSeq 6000 S2", "Illumina", 2, 1650)
    NOVSASEQ_6K_S4 = FlowCellTypeEnum(4, "NovaSeq 6000 S4", "Illumina", 4, 2000)

    MISEQ_V3 = FlowCellTypeEnum(10, "MiSeq v3", "Illumina", 1, 22)
    MISEQ_V2 = FlowCellTypeEnum(11, "MiSeq v2", "Illumina", 1, 12)
    MISEQ_MICRO_V2 = FlowCellTypeEnum(12, "MiSeq Micro v2", "Illumina", 1, 4)
    MISEQ_NANO_V2 = FlowCellTypeEnum(13, "MiSeq Nano v2", "Illumina", 1, 1)

    NOVASEQ_X_1B_ILLUMINA = FlowCellTypeEnum(100, "NovaSeq X 1.5B", "Illumina", 8, 200)
    NOVASEQ_X_10B_ILLUMINA = FlowCellTypeEnum(101, "NovaSeq X 10B", "Illumina", 8, 1250)
    NOVASEQ_X_25B_ILLUMINA = FlowCellTypeEnum(102, "NovaSeq X 25B", "Illumina", 8, 3250)
