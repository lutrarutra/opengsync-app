from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class LibraryTypeEnum(DBEnum):
    abbreviation: str
    assay_type: str
    modality: str

    @property
    def select_name(self) -> str:
        return self.abbreviation


class LibraryType(ExtendedEnum[LibraryTypeEnum], enum_type=LibraryTypeEnum):
    CUSTOM = LibraryTypeEnum(0, "Custom", "Custom", "Custom", "Custom")
    SC_RNA_SEQ = LibraryTypeEnum(1, "Single-cell RNA-seq", "scRNA-seq", "GEX", "Gene Expression")
    SN_RNA_SEQ = LibraryTypeEnum(2, "Single-nucleus RNA-seq", "snRNA-seq", "GEX", "Gene Expression")
    MULTIPLEXING_CAPTURE = LibraryTypeEnum(3, "Multiplexing Capture", "CMO", "CMO", "Multiplexing Capture")
    SC_ATAC = LibraryTypeEnum(4, "Single-cell Chromatin Accessibility", "scATAC-seq", "ATAC", "Chromatin Accessibility")
    SN_ATAC = LibraryTypeEnum(5, "Single-nucleus Chromatin Accessibility", "snATAC-seq", "ATAC", "Chromatin Accessibility")
    SPATIAL_TRANSCRIPTOMIC = LibraryTypeEnum(6, "Spatial transcriptomic", "VISIUM", "VISIUM", "Spatial Transcriptomics")
    VDJ_B = LibraryTypeEnum(7, "VDJ-B", "VDJ-B", "VDJ-B", "VDJ-B")
    VDJ_T = LibraryTypeEnum(8, "VDJ-T", "VDJ-T", "VDJ-T", "VDJ-T")
    VDJ_T_GD = LibraryTypeEnum(9, "VDJ-T-GD", "VDJ-T-GD", "VDJ-T-GD", "VDJ-T-GD")
    ANTIBODY_CAPTURE = LibraryTypeEnum(10, "Antibody Capture", "ABC", "ABC", "Antibody Capture")
    CRISPR = LibraryTypeEnum(11, "CRISPR Guide Capture", "CRISPR", "CRISPR", "CRISPR Guide Capture")
    BULK_RNA_SEQ = LibraryTypeEnum(100, "Bulk RNA-seq", "BULK", "GEX", "Gene Expression")
    EXOME_SEQ = LibraryTypeEnum(101, "Exome-seq", "EXOME", "EXOME", "Gene Expression")
    GENOME_SEQ = LibraryTypeEnum(102, "Genome-seq", "GENOME", "GENOME", "Gene Expression")
    AMPLICON_SEQ = LibraryTypeEnum(103, "Amplicon-seq", "AMPLICON", "AMPLICON", "Gene Expression")
    RBS_SEQ = LibraryTypeEnum(104, "RBS-seq", "RBS", "RBS", "Gene Expression")
    CITE_SEQ = LibraryTypeEnum(105, "CITE-seq", "CITE", "CITE", "Cell Surface Protein Quantification")
    ATAC_SEQ = LibraryTypeEnum(106, "ATAC-seq", "ATAC", "ATAC", "Chromatin Accessibility")
