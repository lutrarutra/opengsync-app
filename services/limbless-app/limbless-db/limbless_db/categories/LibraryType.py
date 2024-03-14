from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class LibraryTypeEnum(DBEnum):
    abbreviation: str
    assay_type: str


class LibraryType(ExtendedEnum[LibraryTypeEnum], enum_type=LibraryTypeEnum):
    CUSTOM = LibraryTypeEnum(0, "Custom", "Custom", "Custom")
    SC_RNA_SEQ = LibraryTypeEnum(1, "Single-cell RNA-seq", "scRNA-seq", "GEX")
    SN_RNA_SEQ = LibraryTypeEnum(2, "Single-nucleus RNA-seq", "snRNA-seq", "GEX")
    MULTIPLEXING_CAPTURE = LibraryTypeEnum(3, "Multiplexing Capture", "CMO", "CMO")
    SC_ATAC = LibraryTypeEnum(4, "Single-cell Chromatin Accessibility", "scATAC-seq", "ATAC")
    SN_ATAC = LibraryTypeEnum(5, "Single-nucleus Chromatin Accessibility", "snATAC-seq", "ATAC")
    SPATIAL_TRANSCRIPTOMIC = LibraryTypeEnum(6, "Spatial transcriptomic", "VISIUM", "VISIUM")
    VDJ_B = LibraryTypeEnum(7, "VDJ-B", "VDJ-B", "VDJ-B")
    VDJ_T = LibraryTypeEnum(8, "VDJ-T", "VDJ-T", "VDJ-T")
    VDJ_T_GD = LibraryTypeEnum(9, "VDJ-T-GD", "VDJ-T-GD", "VDJ-T-GD")
    ANTIBODY_CAPTURE = LibraryTypeEnum(10, "Antibody Capture", "ABC", "ABC")
    CRISPR = LibraryTypeEnum(11, "CRISPR", "CRISPR", "CRISPR")
    BULK_RNA_SEQ = LibraryTypeEnum(100, "Bulk RNA-seq", "BULK", "GEX")
    EXOME_SEQ = LibraryTypeEnum(101, "Exome-seq", "EXOME", "EXOME")
    GENOME_SEQ = LibraryTypeEnum(102, "Genome-seq", "GENOME", "GENOME")
    AMPLICON_SEQ = LibraryTypeEnum(103, "Amplicon-seq", "AMPLICON", "AMPLICON")
    RBS_SEQ = LibraryTypeEnum(104, "RBS-seq", "RBS", "RBS")
    CITE_SEQ = LibraryTypeEnum(105, "CITE-seq", "CITE", "CITE")
    ATAC_SEQ = LibraryTypeEnum(106, "ATAC-seq", "ATAC", "ATAC")
