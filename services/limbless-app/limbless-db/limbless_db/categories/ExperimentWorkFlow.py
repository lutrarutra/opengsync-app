from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum

from .FlowCellType import FlowCellType, FlowCellTypeEnum


@dataclass(eq=False)
class ExperimentWorkFlowEnum(DBEnum):
    volume_target_ul: float
    flow_cell_type: FlowCellTypeEnum
    combined_lanes: bool = False


class ExperimentWorkFlow(ExtendedEnum[ExperimentWorkFlowEnum], enum_type=ExperimentWorkFlowEnum):
    NOVASEQ_SP_STD = ExperimentWorkFlowEnum(1, "NovaSeq SP Standard", 120, FlowCellType.SP_ILLUMINA, True)
    NOVASEQ_SP_XP = ExperimentWorkFlowEnum(2, "NovaSeq SP XP", 30, FlowCellType.SP_ILLUMINA)
    
    NOVASEQ_S1_STD = ExperimentWorkFlowEnum(3, "NovaSeq S1 Standard", 120, FlowCellType.S1_ILLUMINA, True)
    NOVASEQ_S1_XP = ExperimentWorkFlowEnum(4, "NovaSeq S1 XP", 30, FlowCellType.S1_ILLUMINA)

    NOVASEQ_S2_STD = ExperimentWorkFlowEnum(5, "NovaSeq S2 Standard", 170, FlowCellType.S2_ILLUMINA, True)
    NOVASEQ_S2_XP = ExperimentWorkFlowEnum(6, "NovaSeq S2 XP", 30, FlowCellType.S2_ILLUMINA)

    NOVASEQ_S4_STD = ExperimentWorkFlowEnum(7, "NovaSeq S4 Standard", 320, FlowCellType.S4_ILLUMINA, True)
    NOVASEQ_S4_XP = ExperimentWorkFlowEnum(8, "NovaSeq S4 XP", 50, FlowCellType.S4_ILLUMINA)

    MISEQ = ExperimentWorkFlowEnum(10, "MiSeq", 20, FlowCellType.MISEQ_ILLUMINA, True)