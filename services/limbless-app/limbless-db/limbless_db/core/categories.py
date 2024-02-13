import os
from enum import Enum

from .EnumType import ExtendedEnumMeta, DescriptiveEnum


class UserResourceRelation(Enum, metaclass=ExtendedEnumMeta):
    OWNER = DescriptiveEnum(1, "Owner")
    CONTRIBUTOR = DescriptiveEnum(2, "Contributor")
    VIEWER = DescriptiveEnum(3, "Viewer")


class UserRole(Enum, metaclass=ExtendedEnumMeta):
    ADMIN = DescriptiveEnum(1, "Admin", "🤓")
    BIOINFORMATICIAN = DescriptiveEnum(2, "Bioinformatician", "👨🏾‍💻")
    TECHNICIAN = DescriptiveEnum(3, "Technician", "🧑🏽‍🔬")
    CLIENT = DescriptiveEnum(4, "Client", "👶🏾")

    @classmethod
    @property
    def insiders(cls):
        return [cls.ADMIN, cls.BIOINFORMATICIAN, cls.TECHNICIAN]


class LibraryType(Enum, metaclass=ExtendedEnumMeta):
    CUSTOM = DescriptiveEnum(0, "Custom")
    SC_RNA_SEQ = DescriptiveEnum(1, "Single-cell RNA-seq", "scRNA-seq")
    SN_RNA_SEQ = DescriptiveEnum(2, "Single-nucleus RNA-seq", "snRNA-seq")
    MULTIPLEXING_CAPTURE = DescriptiveEnum(3, "Multiplexing Capture", "CMO")
    SC_ATAC = DescriptiveEnum(4, "Single-cell Chromatin Accessibility", "scATAC-seq")
    SN_ATAC = DescriptiveEnum(5, "Single-nucleus Chromatin Accessibility", "snATAC-seq")
    SPATIAL_TRANSCRIPTOMIC = DescriptiveEnum(6, "Spatial transcriptomic", "VISIUM")
    VDJ_B = DescriptiveEnum(7, "VDJ-B", "VDJ-B")
    VDJ_T = DescriptiveEnum(8, "VDJ-T", "VDJ-T")
    VDJ_T_GD = DescriptiveEnum(9, "VDJ-T-GD", "VDJ-T-GD")
    ANTIBODY_CAPTURE = DescriptiveEnum(10, "Antibody Capture", "ABC")
    CRISPR = DescriptiveEnum(11, "CRISPR", "CRISPR")
    BULK_RNA_SEQ = DescriptiveEnum(100, "Bulk RNA-seq", "BULK")
    EXOME_SEQ = DescriptiveEnum(101, "Exome-seq", "EXOME")
    GENOME_SEQ = DescriptiveEnum(102, "Genome-seq", "GENOME")
    AMPLICON_SEQ = DescriptiveEnum(103, "Amplicon-seq", "AMPLICON")
    RBS_SEQ = DescriptiveEnum(104, "RBS-seq", "RBS")
    CITE_SEQ = DescriptiveEnum(105, "CITE-seq", "CITE")
    ATAC_SEQ = DescriptiveEnum(106, "ATAC-seq", "ATAC")

    @staticmethod
    def technical_abbreviation(library_type: "LibraryType") -> str:
        return {
            0: "",
            1: "GEX",
            2: "GEX",
            3: "CMO",
            4: "ATAC",
            5: "ATAC",
            6: "VISIUM",
            7: "VDJ-B",
            8: "VDJ-T",
            9: "VDJ-T-GD",
            10: "ABC",
            11: "CRISPR",
            100: "GEX",
            101: "EXOME",
            102: "GENOME",
            103: "AMPLICON",
            104: "RBS",
            105: "CITE",
            106: "ATAC",
        }[library_type.value.id]


class FlowCellType(Enum, metaclass=ExtendedEnumMeta):
    OTHER = DescriptiveEnum(0, "Other")
    NOVASEQ_SP = DescriptiveEnum(1, "NovaSeq SP")
    NOVASEQ_S1 = DescriptiveEnum(2, "NovaSeq S1")
    NOVASEQ_S2 = DescriptiveEnum(3, "NovaSeq S2")
    NOVASEQ_S4 = DescriptiveEnum(4, "NovaSeq S4")
    NOVASEQ_SP_XP = DescriptiveEnum(5, "NovaSeq SP XP")
    MI_SEQ_V3 = DescriptiveEnum(6, "MiSeq V3")
    MI_SEQ_V2_MICRO = DescriptiveEnum(7, "MiSeq V2 Micro")
    NOVASEQ_S4_SP = DescriptiveEnum(8, "NovaSeq S4 SP")
    MI_SEQ_V2_NANO = DescriptiveEnum(9, "MiSeq V2 Nano")


class IndexKitType(Enum, metaclass=ExtendedEnumMeta):
    CUSTOM = DescriptiveEnum(0, "Custom")
    TENX = DescriptiveEnum(1, "10x")


class OrganismCategory(Enum, metaclass=ExtendedEnumMeta):
    UNCLASSIFIED = DescriptiveEnum(0, "Unclassified")
    ARCHAEA = DescriptiveEnum(1, "Archaea")
    BACTERIA = DescriptiveEnum(2, "Bacteria")
    EUKARYOTA = DescriptiveEnum(3, "Eukaryota")
    VIRUSES = DescriptiveEnum(4, "Viruses")
    OTHER = DescriptiveEnum(5, "Other")


class AccessType(Enum, metaclass=ExtendedEnumMeta):
    READWRITE = DescriptiveEnum(1, "Read/Write")
    READ = DescriptiveEnum(2, "Read")


class SeqRequestStatus(Enum, metaclass=ExtendedEnumMeta):
    DRAFT = DescriptiveEnum(0, "Draft", description="✍🏼")
    SUBMITTED = DescriptiveEnum(1, "Submitted", description="🚀")
    PREPARATION = DescriptiveEnum(2, "Sequencing Preparation", description="🧪")
    SEQUENCING = DescriptiveEnum(3, "Sequencing", description="🧬")
    DATA_PROCESSING = DescriptiveEnum(4, "Data Processing", description="👨🏽‍💻")
    FINISHED = DescriptiveEnum(5, "Finished", description="✅")
    ARCHIVED = DescriptiveEnum(6, "Archived", description="🗃️")
    FAILED = DescriptiveEnum(7, "Failed", description="❌")


class ExperimentStatus(Enum, metaclass=ExtendedEnumMeta):
    DRAFT = DescriptiveEnum(0, "Draft", description="✍🏼")
    SEQUENCING = DescriptiveEnum(1, "Sequencing", description="🧬")
    FINISHED = DescriptiveEnum(2, "Finished", description="✅")
    ARCHIVED = DescriptiveEnum(3, "Archived", description="🗃️")
    FAILED = DescriptiveEnum(4, "Failed", description="❌")


class HttpResponse(Enum, metaclass=ExtendedEnumMeta):
    OK = DescriptiveEnum(200, "OK")
    BAD_REQUEST = DescriptiveEnum(400, "Bad Request")
    UNAUTHORIZED = DescriptiveEnum(401, "Unauthorized")
    FORBIDDEN = DescriptiveEnum(403, "Forbidden")
    NOT_FOUND = DescriptiveEnum(404, "Not Found")
    METHOD_NOT_ALLOWED = DescriptiveEnum(405, "Method Not Allowed")
    INTERNAL_SERVER_ERROR = DescriptiveEnum(500, "Internal Server Error")
    

class BarcodeType(Enum, metaclass=ExtendedEnumMeta):
    INDEX_1 = DescriptiveEnum(1, "Index 1")
    INDEX_2 = DescriptiveEnum(2, "Index 2")
    INDEX_3 = DescriptiveEnum(3, "Index 3")
    INDEX_4 = DescriptiveEnum(4, "Index 4")
    # INDEX_I7 = DescriptiveEnum(5, "Index I7")
    # INDEX_I5 = DescriptiveEnum(6, "Index I5")

    @staticmethod
    def mapping(type_id: int) -> str:
        return {
            BarcodeType.INDEX_1.value.id: "index_1",
            BarcodeType.INDEX_2.value.id: "index_2",
            BarcodeType.INDEX_3.value.id: "index_3",
            BarcodeType.INDEX_4.value.id: "index_4",
            # BarcodeType.INDEX_I7.value.id: "index_1",
            # BarcodeType.INDEX_I5.value.id: "index_2",
        }[type_id]
    

class FeatureType(Enum, metaclass=ExtendedEnumMeta):
    CUSTOM = DescriptiveEnum(0, "Custom")
    CMO = DescriptiveEnum(1, "Cell Multiplexing Oligo", "CMO")
    ANTIBODY = DescriptiveEnum(2, "Antibody", "ABC")
    CRISPR_CAPTURE = DescriptiveEnum(3, "CRISPR Capture", "CRISPR")
    GENE_CAPTURE = DescriptiveEnum(4, "Gene Capture", "GENE")
    PRIMER_CAPTURE = DescriptiveEnum(5, "Primer Capture", "PRIMER")
    

class SequencingType(Enum, metaclass=ExtendedEnumMeta):
    OTHER = DescriptiveEnum(0, "Other", "⚙️")
    SINGLE_END = DescriptiveEnum(1, "Single-end", "➡️")
    PAIRED_END = DescriptiveEnum(2, "Paired-end", "🔁")


class RequestResponse(Enum, metaclass=ExtendedEnumMeta):
    ACCEPTED = DescriptiveEnum(1, "Accepted", "✅")
    REJECTED = DescriptiveEnum(2, "Rejected", "❌")
    PENDING_REVISION = DescriptiveEnum(3, "Pending Revision", "🔍")


class FileType(Enum, metaclass=ExtendedEnumMeta):
    CUSTOM = DescriptiveEnum(0, "Custom", os.path.join("media", "etc"))
    SEQ_AUTH_FORM = DescriptiveEnum(1, "Sequencing Authorization Form", os.path.join("media", "seq_auth_forms"))
    BIOANALYZER_REPORT = DescriptiveEnum(2, "Bioanalyzer Report", os.path.join("media", "bioanalyzer_reports"))
    POST_SEQUENCING_QC_REPORT = DescriptiveEnum(3, "Post-sequencing QC Report", os.path.join("media", "post_seq_qc_reports"))

    