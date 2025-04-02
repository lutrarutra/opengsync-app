from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class LabProtocolEnum(DBEnum):
    abbreviation: str
    identifier: str
    prep_file_name: str


class LabProtocol(ExtendedEnum[LabProtocolEnum], enum_type=LabProtocolEnum):
    CUSTOM = LabProtocolEnum(0, "Custom", "Custom", "", "template.xlsx")
    RNA_SEQ = LabProtocolEnum(1, "RNA-seq", "RNA", "R", "RNA.xlsx")
    QUANT_SEQ = LabProtocolEnum(2, "Quant-seq", "QUANT", "Q", "QUANTSEQ.xlsx")
    SMART_SEQ = LabProtocolEnum(3, "Smart-seq", "SMART", "S", "SMARTSEQ.xlsx")
    WGS = LabProtocolEnum(4, "Whole Genome Sequencing", "WGS", "W", "WGS_COV.xlsx")
    TENX = LabProtocolEnum(5, "10X Genomics", "10x", "T", "TENX.xlsx")
    WES = LabProtocolEnum(6, "Whole Exome Sequencing", "WES", "E", "WGS_COV.xlsx")