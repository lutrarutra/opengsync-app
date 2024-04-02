from dataclasses import dataclass, field

from .ExtendedEnum import DBEnum, ExtendedEnum

from .SequencingWorkFlowType import SequencingWorkFlowType, SequencingWorkFlowTypeEnum


@dataclass
class FlowCellTypeEnum(DBEnum):
    manufacturer: str
    num_lanes: int
    max_m_reads_per_lane: int

    supported_workflows: list[SequencingWorkFlowTypeEnum] = field(default_factory=list)


# https://emea.illumina.com/systems/sequencing-platforms/novaseq/specifications.html
class FlowCellType(ExtendedEnum[FlowCellTypeEnum], enum_type=FlowCellTypeEnum):
    SP_ILLUMINA = FlowCellTypeEnum(1, "SP", "Illumina", 2, 650, [SequencingWorkFlowType.NOVASEQ_SP_STD, SequencingWorkFlowType.NOVASEQ_SP_XP])
    S1_ILLUMINA = FlowCellTypeEnum(2, "S1", "Illumina", 2, 1300, [SequencingWorkFlowType.NOVASEQ_S1_STD, SequencingWorkFlowType.NOVASEQ_S1_XP])
    S2_ILLUMINA = FlowCellTypeEnum(3, "S2", "Illumina", 2, 3300, [SequencingWorkFlowType.NOVASEQ_S2_STD, SequencingWorkFlowType.NOVASEQ_S2_XP])
    S4_ILLUMINA = FlowCellTypeEnum(4, "S4", "Illumina", 4, 8000, [SequencingWorkFlowType.NOVASEQ_S4_STD, SequencingWorkFlowType.NOVASEQ_S4_XP])
