from typing import Optional
from dataclasses import dataclass, field

from .ExtendedEnum import DBEnum, ExtendedEnum
from .LibraryType import LibraryType, LibraryTypeEnum


@dataclass(eq=False, frozen=True)
class ServiceTypeEnum(DBEnum):
    label: str
    abbreviation: str
    platform: str | None = None
    oligo_multiplexing: bool = False
    ocm_multiplexing: bool = False
    library_types: list[LibraryType] = field(default_factory=list)
    optional_library_types: list[LibraryType] = field(default_factory=list)


class ServiceType(ExtendedEnum):
    label: str
    abbreviation: str
    platform: str | None
    oligo_multiplexing: bool
    ocm_multiplexing: bool
    library_types: list[LibraryType]
    optional_library_types: list[LibraryType]
    CUSTOM = ServiceTypeEnum(0, "Custom", "Custom")

    # 10x Genomics: https://www.10xgenomics.com/products
    TENX_SC_SINGLE_PLEX_FLEX = ServiceTypeEnum(10, "10X Single Cell Gene Expression Flex Single-Plex", "10X Flex Single-Plex", "10X Chromium", library_types=[LibraryType.TENX_SC_GEX_FLEX], optional_library_types=[LibraryType.TENX_SC_ABC_FLEX])
    TENX_SC_ATAC = ServiceTypeEnum(11, "10X Single Cell ATAC", "10X ATAC", "10X Chromium", library_types=[LibraryType.TENX_SC_ATAC])
    TENX_SC_GEX_3PRIME = ServiceTypeEnum(12, "10X Single Cell Gene Expression 3'", "10X 3'", "10X Chromium", oligo_multiplexing=True, ocm_multiplexing=True, library_types=[LibraryType.TENX_SC_GEX_3PRIME], optional_library_types=[LibraryType.TENX_ANTIBODY_CAPTURE])
    TENX_SC_GEX_5PRIME = ServiceTypeEnum(13, "10X Single Cell Immune Profiling 5'", "10X 5'", "10X Chromium", oligo_multiplexing=True, ocm_multiplexing=True, library_types=[LibraryType.TENX_SC_GEX_5PRIME], optional_library_types=[LibraryType.TENX_ANTIBODY_CAPTURE, LibraryType.TENX_CRISPR_SCREENING, LibraryType.TENX_VDJ_B, LibraryType.TENX_VDJ_T, LibraryType.TENX_VDJ_T_GD])
    TENX_SC_MULTIOME = ServiceTypeEnum(14, "10X Single Cell Multiome", "10X Multiome", "10X Chromium", oligo_multiplexing=True, library_types=[LibraryType.TENX_SC_GEX_3PRIME, LibraryType.TENX_SC_ATAC])
    TENX_SC_4_PLEX_FLEX = ServiceTypeEnum(15, "10X Single Cell Gene Expression Flex 4-Plex", "10X Flex 4-Plex", "10X Chromium", library_types=[LibraryType.TENX_SC_GEX_FLEX], optional_library_types=[LibraryType.TENX_SC_ABC_FLEX])
    TENX_SC_16_PLEX_FLEX = ServiceTypeEnum(16, "10X Single Cell Gene Expression Flex 16-Plex", "10X Flex 16-Plex", "10X Chromium", library_types=[LibraryType.TENX_SC_GEX_FLEX], optional_library_types=[LibraryType.TENX_SC_ABC_FLEX])

    # Special
    OPENST = ServiceTypeEnum(50, "Open Spatial Transcriptomics", "Open-ST", library_types=[LibraryType.OPENST])
    PARSE = ServiceTypeEnum(51, "Parse Biosciences Single-Cell Sequencing", "Parse SC", library_types=[LibraryType.PARSE_SC_GEX], optional_library_types=[LibraryType.PARSE_SC_CRISPR, LibraryType.PARSE_EVERCODE_TCR, LibraryType.PARSE_EVERCODE_BCR])

    # RNA
    BULK_RNA_SEQ = ServiceTypeEnum(100, "Bulk RNA-Seq", "Bulk RNA-Seq", library_types=[LibraryType.BULK_RNA_SEQ])
    
    WGS = ServiceTypeEnum(105, "Whole Genome Sequencing", "WGS", library_types=[LibraryType.WGS])
    WES = ServiceTypeEnum(106, "Whole Exome Sequencing", "WES", library_types=[LibraryType.WES])
    
    # EM
    WG_BS_SEQ = ServiceTypeEnum(107, "Whole Genome Bisulfite Sequencing", "WG BS-Seq", library_types=[LibraryType.WG_BS_SEQ])
    RR_BS_SEQ = ServiceTypeEnum(108, "Reduced Representation Bisulfite Sequencing", "RR BS-Seq", library_types=[LibraryType.RR_BS_SEQ])
    WG_EM_SEQ = ServiceTypeEnum(109, "Whole Genome Enzymatic Methylation Sequencing", "WG EM-Seq", library_types=[LibraryType.WG_EM_SEQ])
    RR_EM_SEQ = ServiceTypeEnum(110, "Reduced Representation Enzymatic Methylation Sequencing", "RR EM-Seq", library_types=[LibraryType.RR_EM_SEQ])
    
    ATAC_SEQ = ServiceTypeEnum(111, "ATAC-Seq", "ATAC-Seq", library_types=[LibraryType.ATAC_SEQ])
    ARTIC_SARS_COV_2 = ServiceTypeEnum(112, "ARTIC SARS-CoV-2", "ARTIC SARS-CoV-2", library_types=[LibraryType.ARTIC_SARS_COV_2])
    IMMUNE_SEQ = ServiceTypeEnum(113, "NEBNext Immune sequencing", "Immune-Seq", library_types=[LibraryType.IMMUNE_SEQ])

    @property
    def display_name(self) -> str:
        return f"{self.label} ({self.abbreviation})"