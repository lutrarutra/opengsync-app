from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum

from .FlowCellType import FlowCellType, FlowCellTypeEnum


@dataclass(eq=False)
class ExperimentWorkFlowEnum(DBEnum):
    volume_target_ul: float
    flow_cell_type: FlowCellTypeEnum
    combined_lanes: bool = False


class ExperimentWorkFlow(ExtendedEnum[ExperimentWorkFlowEnum], enum_type=ExperimentWorkFlowEnum):
    NOVASEQ_6K_SP_STD = ExperimentWorkFlowEnum(1, "NovaSeq SP Standard", 120, FlowCellType.NOVSASEQ_6K_SP, True)
    NOVASEQ_6K_SP_XP = ExperimentWorkFlowEnum(2, "NovaSeq SP XP", 30, FlowCellType.NOVSASEQ_6K_SP)
    
    NOVASEQ_6K_S1_STD = ExperimentWorkFlowEnum(3, "NovaSeq S1 Standard", 120, FlowCellType.NOVSASEQ_6K_S1, True)
    NOVASEQ_6K_S1_XP = ExperimentWorkFlowEnum(4, "NovaSeq S1 XP", 30, FlowCellType.NOVSASEQ_6K_S1)

    NOVASEQ_6K_S2_STD = ExperimentWorkFlowEnum(5, "NovaSeq S2 Standard", 170, FlowCellType.NOVSASEQ_6K_S2, True)
    NOVASEQ_6K_S2_XP = ExperimentWorkFlowEnum(6, "NovaSeq S2 XP", 30, FlowCellType.NOVSASEQ_6K_S2)

    NOVASEQ_6K_S4_STD = ExperimentWorkFlowEnum(7, "NovaSeq S4 Standard", 320, FlowCellType.NOVSASEQ_6K_S4, True)
    NOVASEQ_6K_S4_XP = ExperimentWorkFlowEnum(8, "NovaSeq S4 XP", 50, FlowCellType.NOVSASEQ_6K_S4)

    MISEQ_v3 = ExperimentWorkFlowEnum(10, "MiSeq v3", 20, FlowCellType.MISEQ_V3, True)
    MISEQ_v2 = ExperimentWorkFlowEnum(11, "MiSeq v2", 21, FlowCellType.MISEQ_V2, True)
    MISEQ_MICRO_v2 = ExperimentWorkFlowEnum(12, "MiSeq Micro v2", 22, FlowCellType.MISEQ_MICRO_V2, True)
    MISEQ_NANO_v2 = ExperimentWorkFlowEnum(13, "MiSeq Nano v2", 23, FlowCellType.MISEQ_NANO_V2, True)

    NOVASEQ_X_1B = ExperimentWorkFlowEnum(100, "NovaSeq X 1.5B", -1, FlowCellType.NOVASEQ_X_1B_ILLUMINA, True)
    NOVASEQ_X_10B = ExperimentWorkFlowEnum(101, "NovaSeq X 10B", -1, FlowCellType.NOVASEQ_X_10B_ILLUMINA, True)
    NOVASEQ_X_25B = ExperimentWorkFlowEnum(102, "NovaSeq X 25B", -1, FlowCellType.NOVASEQ_X_25B_ILLUMINA, True)

    NOVASEQ_X_1B_XP = ExperimentWorkFlowEnum(103, "NovaSeq X 1.5B XP", -1, FlowCellType.NOVASEQ_X_1B_ILLUMINA)
    NOVASEQ_X_10B_XP = ExperimentWorkFlowEnum(104, "NovaSeq X 10B XP", -1, FlowCellType.NOVASEQ_X_10B_ILLUMINA)
    NOVASEQ_X_25B_XP = ExperimentWorkFlowEnum(105, "NovaSeq X 25B XP", -1, FlowCellType.NOVASEQ_X_25B_ILLUMINA)


    @classmethod
    def novaseq_6k_workflows(cls) -> list["ExperimentWorkFlowEnum"]:
        return [
            cls.NOVASEQ_6K_SP_STD,
            cls.NOVASEQ_6K_SP_XP,
            cls.NOVASEQ_6K_S1_STD,
            cls.NOVASEQ_6K_S1_XP,
            cls.NOVASEQ_6K_S2_STD,
            cls.NOVASEQ_6K_S2_XP,
            cls.NOVASEQ_6K_S4_STD,
            cls.NOVASEQ_6K_S4_XP,
        ]
    
    @classmethod
    def miseq_workflows(cls) -> list["ExperimentWorkFlowEnum"]:
        return [
            cls.MISEQ_v3,
            cls.MISEQ_v2,
            cls.MISEQ_MICRO_v2,
            cls.MISEQ_NANO_v2,
        ]
    
    @classmethod
    def novaseq_x_workflows(cls) -> list["ExperimentWorkFlowEnum"]:
        return [
            cls.NOVASEQ_X_1B,
            cls.NOVASEQ_X_10B,
            cls.NOVASEQ_X_25B,
            cls.NOVASEQ_X_1B_XP,
            cls.NOVASEQ_X_10B_XP,
            cls.NOVASEQ_X_25B_XP,
        ]