from typing import Optional
from dataclasses import dataclass, field

from .ExtendedEnum import DBEnum, ExtendedEnum
from .LibraryType import LibraryType, LibraryTypeEnum


@dataclass
class AssayTypeEnum(DBEnum):
    abbreviation: str
    platform: Optional[str] = None
    can_be_multiplexed: bool = False
    library_types: list[LibraryTypeEnum] = field(default_factory=list)
    optional_library_types: list[LibraryTypeEnum] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        return f"{self.name} ({self.abbreviation})"


# https://www.10xgenomics.com/products
class AssayType(ExtendedEnum[AssayTypeEnum], enum_type=AssayTypeEnum):
    CUSTOM = AssayTypeEnum(0, "Custom", "Custom")

    # 10x Genomics
    TENX_SC_SINGLE_PLEX_FLEX = AssayTypeEnum(10, "10X Single Cell Gene Expression Flex Single-Plex", "10X Flex Single-Plex", "10X Chromium", library_types=[LibraryType.TENX_SC_GEX_FLEX], optional_library_types=[LibraryType.TENX_SC_ABC_FLEX])
    TENX_SC_ATAC = AssayTypeEnum(11, "10X Single Cell ATAC", "10X ATAC", "10X Chromium", library_types=[LibraryType.TENX_SC_ATAC])
    TENX_SC_GEX_3PRIME = AssayTypeEnum(12, "10X Single Cell Gene Expression 3'", "10X 3'", "10X Chromium", can_be_multiplexed=True, library_types=[LibraryType.TENX_SC_GEX_3PRIME], optional_library_types=[LibraryType.TENX_ANTIBODY_CAPTURE])
    TENX_SC_GEX_5PRIME = AssayTypeEnum(13, "10X Single Cell Immune Profiling 5'", "10X 5'", "10X Chromium", can_be_multiplexed=True, library_types=[LibraryType.TENX_SC_GEX_5PRIME], optional_library_types=[LibraryType.TENX_ANTIBODY_CAPTURE, LibraryType.TENX_CRISPR_SCREENING, LibraryType.TENX_VDJ_B, LibraryType.TENX_VDJ_T, LibraryType.TENX_VDJ_T_GD])
    TENX_SC_MULTIOME = AssayTypeEnum(14, "10X Single Cell Multiome", "10X Multiome", "10X Chromium", library_types=[LibraryType.TENX_SC_GEX_3PRIME, LibraryType.TENX_SC_ATAC])
    TENX_SC_4_PLEX_FLEX = AssayTypeEnum(15, "10X Single Cell Gene Expression Flex 4-Plex", "10X Flex 4-Plex", "10X Chromium", library_types=[LibraryType.TENX_SC_GEX_FLEX], optional_library_types=[LibraryType.TENX_ANTIBODY_CAPTURE])
    TENX_SC_16_PLEX_FLEX = AssayTypeEnum(16, "10X Single Cell Gene Expression Flex 16-Plex", "10X Flex 16-Plex", "10X Chromium", library_types=[LibraryType.TENX_SC_GEX_FLEX], optional_library_types=[LibraryType.TENX_ANTIBODY_CAPTURE])

    # RNA
    POLY_A_RNA_SEQ = AssayTypeEnum(101, "Poly-A RNA-Seq", "Poly-A RNA-Seq", library_types=[LibraryType.POLY_A_RNA_SEQ])
    RIBO_DEPL_RNA_SEQ = AssayTypeEnum(102, "Ribo Depletion RNA-Seq", "Ribo Depletion RNA-Seq", library_types=[LibraryType.RIBO_DEPL_RNA_SEQ])
    QUANT_SEQ = AssayTypeEnum(103, "Transcription fingerprinting 3' RNA-seq protocol", "Quant-Seq", library_types=[LibraryType.QUANT_SEQ])
    SMART_SEQ = AssayTypeEnum(104, "Full-length RNA-seq from single cells using Smart-seq2", "SMART-Seq", library_types=[LibraryType.SMART_SEQ])
    
    WGS = AssayTypeEnum(105, "Whole Genome Sequencing", "WGS", library_types=[LibraryType.WGS])
    WES = AssayTypeEnum(106, "Whole Exome Sequencing", "WES", library_types=[LibraryType.WES])
    
    # EM
    WG_BS_SEQ = AssayTypeEnum(107, "Whole Genome Bisulfite Sequencing", "WG BS-Seq", library_types=[LibraryType.WG_BS_SEQ])
    RR_BS_SEQ = AssayTypeEnum(108, "Reduced Representation Bisulfite Sequencing", "RR BS-Seq", library_types=[LibraryType.RR_BS_SEQ])
    WG_EM_SEQ = AssayTypeEnum(109, "Whole Genome Enzymatic Methylation Sequencing", "WG EM-Seq", library_types=[LibraryType.WG_EM_SEQ])
    RR_EM_SEQ = AssayTypeEnum(110, "Reduced Representation Enzymatic Methylation Sequencing", "RR EM-Seq", library_types=[LibraryType.RR_EM_SEQ])
    
    ATAC_SEQ = AssayTypeEnum(111, "ATAC-Seq", "ATAC-Seq", library_types=[LibraryType.ATAC_SEQ])
    ARTIC_SARS_COV_2 = AssayTypeEnum(112, "ARTIC SARS-CoV-2", "ARTIC SARS-CoV-2", library_types=[LibraryType.ARTIC_SARS_COV_2])
    IMMUNE_SEQ = AssayTypeEnum(113, "NEBNext Immune sequencing", "Immune-Seq", library_types=[LibraryType.IMMUNE_SEQ])