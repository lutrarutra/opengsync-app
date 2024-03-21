from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class SequencerTypeEnum(DBEnum):
    manufacturer: str

    @property
    def display_name(self) -> str:
        return f"{self.name} ({self.manufacturer})"


class SequencerType(ExtendedEnum[SequencerTypeEnum], enum_type=SequencerTypeEnum):
    I_SEQ_100 = SequencerTypeEnum(1, "iSeq 100", "Illumina")
    MINI_SEQ = SequencerTypeEnum(2, "MiniSeq", "Illumina")
    MI_SEQ = SequencerTypeEnum(3, "MiSeq", "Illumina")
    NEXT_SEQ_550 = SequencerTypeEnum(4, "NextSeq 550", "Illumina")
    NEXT_SEQ_1000 = SequencerTypeEnum(5, "NextSeq 1000", "Illumina")
    NEXT_SEQ_2000 = SequencerTypeEnum(6, "NextSeq 2000", "Illumina")
    NOVA_SEQ_6000 = SequencerTypeEnum(7, "NovaSeq 6000", "Illumina")
    NOVA_SEQ_X = SequencerTypeEnum(8, "NovaSeq X", "Illumina")