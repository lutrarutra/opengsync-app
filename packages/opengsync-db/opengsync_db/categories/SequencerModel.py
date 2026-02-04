from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False, frozen=True)
class SequencerModelEnum(DBEnum):
    label: str
    manufacturer: str


class SequencerModel(ExtendedEnum):
    label: str
    manufacturer: str
    I_SEQ_100 = SequencerModelEnum(1, "iSeq 100", "Illumina")
    MINI_SEQ = SequencerModelEnum(2, "MiniSeq", "Illumina")
    MI_SEQ = SequencerModelEnum(3, "MiSeq", "Illumina")
    NEXT_SEQ_550 = SequencerModelEnum(4, "NextSeq 550", "Illumina")
    NEXT_SEQ_1000 = SequencerModelEnum(5, "NextSeq 1000", "Illumina")
    NEXT_SEQ_2000 = SequencerModelEnum(6, "NextSeq 2000", "Illumina")
    NOVA_SEQ_6000 = SequencerModelEnum(7, "NovaSeq 6000", "Illumina")
    NOVA_SEQ_X = SequencerModelEnum(8, "NovaSeq X", "Illumina")

    @property
    def display_name(self) -> str:
        return f"{self.label} ({self.manufacturer})"