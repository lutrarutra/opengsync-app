from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class LabProtocolEnum(DBEnum):
    abbreviation: str
    identifier: str


class LabProtocol(ExtendedEnum[LabProtocolEnum], enum_type=LabProtocolEnum):
    CUSTOM = LabProtocolEnum(0, "Custom", "Custom", "")
    RNA_SEQ = LabProtocolEnum(1, "RNA-seq", "RNA", "R")
    QUANT_SEQ = LabProtocolEnum(2, "Quant-seq", "QUANT", "Q")
    SMART_SEQ = LabProtocolEnum(3, "Smart-seq", "SMART", "S")
    WGS = LabProtocolEnum(4, "Whole Genome Sequencing", "WGS", "W")
    TENX = LabProtocolEnum(5, "10X Genomics", "10x", "T")
    WES = LabProtocolEnum(6, "Whole Exome Sequencing", "WES", "E")