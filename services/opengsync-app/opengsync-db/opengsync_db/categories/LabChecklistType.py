from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False)
class LabChecklistTypeEnum(DBEnum):
    abbreviation: str
    identifier: str
    prep_file_name: str


class LabChecklistType(ExtendedEnum[LabChecklistTypeEnum], enum_type=LabChecklistTypeEnum):
    CUSTOM = LabChecklistTypeEnum(0, "Custom", "Custom", "X", "template.xlsx")
    RNA_SEQ = LabChecklistTypeEnum(1, "RNA-seq", "RNA", "R", "RNA.xlsx")
    QUANT_SEQ = LabChecklistTypeEnum(2, "Quant-seq", "QUANT", "Q", "QUANTSEQ.xlsx")
    SMART_SEQ = LabChecklistTypeEnum(3, "Smart-seq", "SMART", "S", "SMARTSEQ.xlsx")
    WGS = LabChecklistTypeEnum(4, "Whole Genome Sequencing", "WGS", "W", "WGS_COV.xlsx")
    TENX = LabChecklistTypeEnum(5, "10X Genomics", "10x", "T", "TENX.xlsx")
    WES = LabChecklistTypeEnum(6, "Whole Exome Sequencing", "WES", "E", "WES.xlsx")
    ATAC_SEQ = LabChecklistTypeEnum(7, "ATAC-seq", "ATAC", "A", "template.xlsx")
    TENX_MULTIOME = LabChecklistTypeEnum(8, "10X Multiome", "10X_MULTIOME", "M", "template.xlsx")