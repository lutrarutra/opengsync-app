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
    MULTIPLEXING_CAPTURE = LibraryTypeEnum(2, "Multiplexing Capture", "HTO", "HTO", "Multiplexing Capture")
    SC_ATAC = LibraryTypeEnum(3, "Single-cell Chromatin Accessibility", "scATAC-seq", "ATAC", "Chromatin Accessibility")
    SPATIAL_TRANSCRIPTOMIC = LibraryTypeEnum(4, "Spatial transcriptomic", "VISIUM", "VISIUM", "Spatial Transcriptomics")
    VDJ_B = LibraryTypeEnum(5, "VDJ-B", "VDJ-B", "VDJB", "VDJ-B")
    VDJ_T = LibraryTypeEnum(6, "VDJ-T", "VDJ-T", "VDJT", "VDJ-T")
    VDJ_T_GD = LibraryTypeEnum(7, "VDJ-T-GD", "VDJ-T-GD", "VDJTGD", "VDJ-T-GD")
    ANTIBODY_CAPTURE = LibraryTypeEnum(8, "Antibody Capture", "ABC", "ABC", "Antibody Capture")
    CRISPR_SCREENING = LibraryTypeEnum(9, "CRISPR Screening", "CRISPR Screening", "CRISPR", "CRISPR Screening")
    TENX_FLEX = LibraryTypeEnum(10, "10x Fixed RNA Profiling (FRP Flex)", "10X Flex", "FRP", "Gene Expression")
    BULK_RNA_SEQ = LibraryTypeEnum(100, "Bulk RNA-seq", "BULK", "RNA", "Gene Expression")
    EXOME_SEQ = LibraryTypeEnum(101, "Exome-seq", "WES", "WES", "Gene Expression")
    GENOME_SEQ = LibraryTypeEnum(102, "Genome-seq", "WGS", "WGS", "Gene Expression")
    AMPLICON_SEQ = LibraryTypeEnum(103, "Amplicon-seq", "Amplicaon-seq", "AMPLICON", "Gene Expression")
    RBS_SEQ = LibraryTypeEnum(104, "RBS-seq", "RBS-seq", "RBS", "Gene Expression")
    CITE_SEQ = LibraryTypeEnum(105, "CITE-seq", "CITE-seq", "CITE", "Cell Surface Protein Quantification")
    ATAC_SEQ = LibraryTypeEnum(106, "ATAC-seq", "ATAC-seq", "CA", "Chromatin Accessibility")
    EM_SEQ = LibraryTypeEnum(107, "Enzymatic Methyl-seq", "EM-seq", "EM", "Methylation Profiling")
    QUANT_SEQ = LibraryTypeEnum(108, "Quant-seq", "QUANT-seq", "QUANT", "Gene Expression")
    SMART_SEQ = LibraryTypeEnum(109, "SMART-seq", "SMART-seq", "SMART", "Gene Expression")
    IMMUNE_SEQ = LibraryTypeEnum(110, "Immune-seq", "Immune-seq", "IMMUNE", "Immune Profiling")
