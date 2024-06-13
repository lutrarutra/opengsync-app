from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class PoolTypeEnum(DBEnum):
    abbreviation: str
    identifier: str


class PoolType(ExtendedEnum[PoolTypeEnum], enum_type=PoolTypeEnum):
    CUSTOM = PoolTypeEnum(0, "Custom", "Custom", "")
    EXTERNAL = PoolTypeEnum(1, "External", "External", "")
    QUANT_SEQ = PoolTypeEnum(2, "Quant-seq", "Quant-seq", "Q")
    SMART_SEQ = PoolTypeEnum(3, "Smart-seq", "Smart-seq", "S")
    WGS = PoolTypeEnum(4, "Whole Genome Sequencing", "WGS", "W")
    TENX = PoolTypeEnum(5, "10X Genomics", "10x", "T")
    RNA_SEQ = PoolTypeEnum(6, "RNA-seq", "RNA-seq", "R")
    EXOME = PoolTypeEnum(7, "Exome-seq", "Exome-seq", "E")