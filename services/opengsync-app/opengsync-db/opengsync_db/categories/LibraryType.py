from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum
from .LabProtocol import LabProtocol, LabProtocolEnum


@dataclass(eq=False)
class LibraryTypeEnum(DBEnum):
    abbreviation: str
    identifier: str
    modality: str

    @property
    def select_name(self) -> str:
        return str(self.id)


class LibraryType(ExtendedEnum[LibraryTypeEnum], enum_type=LibraryTypeEnum):
    CUSTOM = LibraryTypeEnum(0, "Custom", "Custom", "Custom", "Custom")

    # 10X Base Technologies
    TENX_SC_GEX_FLEX = LibraryTypeEnum(1, "10X Flex Gene Expression", "10X Flex GEX", "10XFLEXGEX", "Gene Expression")
    TENX_SC_ATAC = LibraryTypeEnum(2, "10X Single Cell ATAC", "10X ATAC", "10XATAC", "Chromatin Accessibility")
    TENX_SC_GEX_3PRIME = LibraryTypeEnum(3, "10X Single Cell 3-P Gene Expression", "10X 3' GEX", "10XGEX3P", "Gene Expression")
    TENX_SC_GEX_5PRIME = LibraryTypeEnum(4, "10X Single Cell 5-P Gene Expression", "10X 5' GEX", "10XGEX5P", "Gene Expression")

    # 10X Visium
    TENX_VISIUM_HD = LibraryTypeEnum(5, "10X HD Spatial Gene Expression", "10X HD Spatial", "10XVISIUMHD", "Spatial Transcriptomics")
    TENX_VISIUM_FFPE = LibraryTypeEnum(6, "10X Visium Gene Expression FFPE", "10X Visium FFPE", "10XVISIUMFFPE", "Spatial Transcriptomics")
    TENX_VISIUM = LibraryTypeEnum(7, "10X Visium Gene Expression", "10X Visium", "10XVISIUM", "Spatial Transcriptomics")
    
    # Optional 10X modalities
    TENX_ANTIBODY_CAPTURE = LibraryTypeEnum(8, "10X Antibody Capture", "10X ABC", "10XABC", "Antibody Capture")
    TENX_MUX_OLIGO = LibraryTypeEnum(9, "10X Multiplexing Oligo Capture", "10X Oligo MUX", "10XOMUX", "Multiplexing Capture")
    TENX_CRISPR_SCREENING = LibraryTypeEnum(10, "10X CRISPR Screening", "10X CRISPR Screening", "10XCRISPR", "CRISPR Screening")
    TENX_VDJ_B = LibraryTypeEnum(11, "10X BCR Profiling (VDJ-B)", "10X VDJ B", "10XVDJB", "VDJ-B")
    TENX_VDJ_T = LibraryTypeEnum(12, "10X TCR alpha-beta Profiling (VDJ-T)", "10X VDJ T", "10XVDJT", "VDJ-T")
    TENX_VDJ_T_GD = LibraryTypeEnum(13, "10X TCR gamma-delta Profiling (VDJ-T-GD)", "10X VDJ T GD", "10XVDJTGD", "VDJ-T-GD")
    TENX_SC_ABC_FLEX = LibraryTypeEnum(14, "10X Flex Antibody Capture", "10X Flex ABC", "10XFLEXABC", "Antibody Capture")

    # Special
    OPENST = LibraryTypeEnum(50, "Open Spatial Transcriptomics", "Open-ST", "OPENST", "Spatial Transcriptomics")

    # RNA-seq
    POLY_A_RNA_SEQ = LibraryTypeEnum(101, "Poly-A RNA-Seq", "Poly-A RNA-Seq", "POLYARNA", "Gene Expression")
    SMART_SEQ = LibraryTypeEnum(102, "SMART-Seq", "SMART-Seq", "SMARTSEQ", "Gene Expression")
    SMART_SC_SEQ = LibraryTypeEnum(103, "SMART-Seq Single Cell", "SMART-Seq SC", "SMARTSEQSC", "Gene Expression")
    RIBO_DEPL_RNA_SEQ = LibraryTypeEnum(104, "Stranded RNA-Seq Ribosomal RNA Depletion", "Ribosomal RNA Depletion", "RRNADEPL", "Gene Expression")
    QUANT_SEQ = LibraryTypeEnum(105, "Transcriptome Fingerprinting 3' RNA-seq", "QUANT-seq", "QUANT", "Gene Expression")

    WGS = LibraryTypeEnum(106, "Whole Genome Sequencing", "WGS", "WGS", "Gene Expression")
    WES = LibraryTypeEnum(107, "Whole Exome Sequencing", "WES", "WES", "Gene Expression")
    ATAC_SEQ = LibraryTypeEnum(108, "ATAC-Seq", "ATAC-Seq", "ATAC", "Chromatin Accessibility")
    
    # EM
    RR_BS_SEQ = LibraryTypeEnum(109, "Reduced Representation Bisulfite Sequencing", "RR BS-Seq", "RRBS", "Methylation Profiling")
    WG_BS_SEQ = LibraryTypeEnum(110, "Whole Genome Bisulfite Sequencing", "WG BS-Seq", "WGBS", "Methylation Profiling")
    RR_EM_SEQ = LibraryTypeEnum(111, "Reduced Representation Enzymatic Methylation Sequencing", "RR EM-seq", "RREMSEQ", "Methylation Profiling")
    WG_EM_SEQ = LibraryTypeEnum(112, "Whole Genome Enzymatic Methylation Sequencing", "WG EM-Seq", "WGEM", "Methylation Profiling")

    ARTIC_SARS_COV_2 = LibraryTypeEnum(113, "ARTIC SARS-CoV-2", "ARTIC SARS-CoV-2", "ARTIC", "Viral Sequencing")
    IMMUNE_SEQ = LibraryTypeEnum(114, "Immune Sequencing", "Immune Sequencing", "IMMUNE", "Immune Sequencing")
    AMPLICON_SEQ = LibraryTypeEnum(115, "Amplicon-seq", "Amplicon-seq", "AMPLICON", "Gene Expression")
    CUT_AND_RUN = LibraryTypeEnum(116, "Cut & Run", "Cut&Run", "CUTNRUN", "Binding Site Quantification")

    @classmethod
    def get_protocol_library_types(cls, lab_protocol: LabProtocolEnum) -> list[LibraryTypeEnum]:
        if lab_protocol == LabProtocol.CUSTOM:
            return LibraryType.as_list()
        return {
            LabProtocol.RNA_SEQ: [LibraryType.POLY_A_RNA_SEQ, LibraryType.IMMUNE_SEQ],
            LabProtocol.QUANT_SEQ: [LibraryType.QUANT_SEQ],
            LabProtocol.SMART_SEQ: [LibraryType.SMART_SEQ, LibraryType.SMART_SC_SEQ],
            LabProtocol.WGS: [LibraryType.WGS, LibraryType.ARTIC_SARS_COV_2, LibraryType.RR_BS_SEQ, LibraryType.WG_BS_SEQ, LibraryType.RR_EM_SEQ, LibraryType.WG_EM_SEQ],
            LabProtocol.WES: [LibraryType.WES],
            LabProtocol.TENX: [
                LibraryType.TENX_SC_GEX_FLEX, LibraryType.TENX_SC_ATAC, LibraryType.TENX_SC_GEX_3PRIME, LibraryType.TENX_SC_GEX_5PRIME,
                LibraryType.TENX_VISIUM_HD, LibraryType.TENX_VISIUM_FFPE, LibraryType.TENX_VISIUM, LibraryType.TENX_ANTIBODY_CAPTURE,
                LibraryType.TENX_MUX_OLIGO, LibraryType.TENX_CRISPR_SCREENING, LibraryType.TENX_VDJ_B, LibraryType.TENX_VDJ_T,
                LibraryType.TENX_VDJ_T_GD, LibraryType.TENX_SC_ABC_FLEX
            ],
        }[lab_protocol]
    
    @classmethod
    def get_visium_library_types(cls) -> list[LibraryTypeEnum]:
        return [
            LibraryType.TENX_VISIUM_HD,
            LibraryType.TENX_VISIUM_FFPE,
            LibraryType.TENX_VISIUM,
        ]
    
    @classmethod
    def get_spatial_library_types(cls) -> list[LibraryTypeEnum]:
        return cls.get_visium_library_types() + [LibraryType.OPENST]
    
    @classmethod
    def get_tenx_library_types(cls) -> list[LibraryTypeEnum]:
        return [
            LibraryType.TENX_SC_GEX_FLEX,
            LibraryType.TENX_SC_ATAC,
            LibraryType.TENX_SC_GEX_3PRIME,
            LibraryType.TENX_SC_GEX_5PRIME,
            LibraryType.TENX_VISIUM_HD,
            LibraryType.TENX_VISIUM_FFPE,
            LibraryType.TENX_VISIUM,
            LibraryType.TENX_ANTIBODY_CAPTURE,
            LibraryType.TENX_MUX_OLIGO,
            LibraryType.TENX_CRISPR_SCREENING,
            LibraryType.TENX_VDJ_B,
            LibraryType.TENX_VDJ_T,
            LibraryType.TENX_VDJ_T_GD,
            LibraryType.TENX_SC_ABC_FLEX
        ]


identifiers = []
for t in LibraryType.as_list():
    if t.identifier in identifiers:
        raise ValueError(f"Duplicate LibraryType identifier: {t}")
    identifiers.append(t.identifier)
    