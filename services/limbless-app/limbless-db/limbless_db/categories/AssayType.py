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
    def select_name(self) -> str:
        return self.abbreviation


# https://www.10xgenomics.com/products
class AssayType(ExtendedEnum[AssayTypeEnum], enum_type=AssayTypeEnum):
    CUSTOM = AssayTypeEnum(0, "Custom", "Custom")

    TENX_SC_GEX_FLEX = AssayTypeEnum(10, "10X Single Cell Gene Expression Flex", "10X Flex", "10X Chromium", True, library_types=[LibraryType.TENX_FLEX], optional_library_types=[LibraryType.ANTIBODY_CAPTURE])
    TENX_SC_ATAC = AssayTypeEnum(11, "10X Single Cell ATAC", "10X ATAC", "10X Chromium", library_types=[LibraryType.SC_ATAC])
    TENX_SC_GEX_3PRIME = AssayTypeEnum(12, "10X Single Cell Gene Expression 3'", "10X 3'", "10X Chromium", True, library_types=[LibraryType.SC_RNA_SEQ], optional_library_types=[LibraryType.ANTIBODY_CAPTURE])
    TENX_SC_IMMUNE_PROFILING_5PRIME = AssayTypeEnum(13, "10X Single Cell Immune Profiling 5'", "10X 5'", "10X Chromium", True, library_types=[LibraryType.SC_RNA_SEQ], optional_library_types=[LibraryType.ANTIBODY_CAPTURE, LibraryType.CRISPR_SCREENING, LibraryType.VDJ_B, LibraryType.VDJ_T, LibraryType.VDJ_T_GD])
    TENX_SC_MULTIOME = AssayTypeEnum(14, "10X Single Cell Multiome", "10X Multiome", "10X Chromium", library_types=[LibraryType.SC_RNA_SEQ, LibraryType.SC_ATAC])
    TENX_HD_SPATIAL_GEX = AssayTypeEnum(15, "10X HD Spatial Gene Expression", "10X HD Spatial", "10X Visium", library_types=[LibraryType.SPATIAL_TRANSCRIPTOMIC])
    TENX_VISIUM_GEX_FFPE = AssayTypeEnum(16, "10X Visium Gene Expression FFPE", "10X Visium FFPE", "10X Visium", library_types=[LibraryType.SPATIAL_TRANSCRIPTOMIC])
    TENX_VISIUM_GEX = AssayTypeEnum(17, "10X Visium Gene Expression", "10X Visium", "10X Visium", library_types=[LibraryType.SPATIAL_TRANSCRIPTOMIC])