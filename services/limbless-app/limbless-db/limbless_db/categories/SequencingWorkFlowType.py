from typing import Optional
from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class SequencingWorkFlowTypeEnum(DBEnum):
    volume_target_ul: Optional[float] = None


class SequencingWorkFlowType(ExtendedEnum[SequencingWorkFlowTypeEnum], enum_type=SequencingWorkFlowTypeEnum):
    NOVASEQ_SP_STD = SequencingWorkFlowTypeEnum(1, "NovaSeq SP Standard", 120)
    NOVASEQ_SP_XP = SequencingWorkFlowTypeEnum(2, "NovaSeq SP XP", 30)
    
    NOVASEQ_S1_STD = SequencingWorkFlowTypeEnum(3, "NovaSeq S1 Standard", 120)
    NOVASEQ_S1_XP = SequencingWorkFlowTypeEnum(4, "NovaSeq S1 XP", 30)

    NOVASEQ_S2_STD = SequencingWorkFlowTypeEnum(5, "NovaSeq S2 Standard", 170)
    NOVASEQ_S2_XP = SequencingWorkFlowTypeEnum(6, "NovaSeq S2 XP", 30)

    NOVASEQ_S4_STD = SequencingWorkFlowTypeEnum(7, "NovaSeq S4 Standard", 320)
    NOVASEQ_S4_XP = SequencingWorkFlowTypeEnum(8, "NovaSeq S4 XP", 50)

    HISEQ = SequencingWorkFlowTypeEnum(9, "HiSeq", 30)
    MISEQ = SequencingWorkFlowTypeEnum(10, "MiSeq", 20)