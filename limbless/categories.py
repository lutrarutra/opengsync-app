from enum import Enum
from .tools.EnumType import ExtendedEnumMeta, DescriptiveEnum


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
    GENE_EXPRESSION = DescriptiveEnum(1, "Gene Expression", "GEX")
    MULTIPLEXING_CAPTURE = DescriptiveEnum(2, "Multiplexing Capture", "HTO")
    CHROMATIN_ACCESSIBILITY = DescriptiveEnum(3, "Chromatin Accessibility", "ATAC")
    SPATIAL_TRANSCRIPTOMIC = DescriptiveEnum(4, "Spatial transcriptomic", "VISIUM")
    VDJ_B = DescriptiveEnum(5, "VDJ-B", "VDJ-B")
    VDJ_T = DescriptiveEnum(6, "VDJ-T", "VDJ-T")
    VDJ_T_GD = DescriptiveEnum(7, "VDJ-T-GD", "VDJ-T-GD")
    ANTIBODY_CAPTURE = DescriptiveEnum(8, "Antibody Capture", "ABC")
    CRISPR = DescriptiveEnum(9, "CRISPR", "CRISPR")


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
    SUBMITTED = DescriptiveEnum(1, "Submitted", description="⏳")
    LIBRARY_PREP = DescriptiveEnum(2, "Library Preparation", description="🧪")
    SEQUENCING = DescriptiveEnum(3, "Sequencing", description="🧬")
    DATA_PROCESSING = DescriptiveEnum(4, "Data Processing", description="👨🏽‍💻")
    FINISHED = DescriptiveEnum(5, "Finished", description="✅")
    ARCHIVED = DescriptiveEnum(6, "Archived", description="🗃️")
    FAILED = DescriptiveEnum(7, "Failed", description="❌")


class ExperimentStatus(Enum, metaclass=ExtendedEnumMeta):
    DRAFT = DescriptiveEnum(0, "Draft", description="✍🏼")
    SUBMITTED = DescriptiveEnum(1, "Submitted", description="⏳")
    SEQUENCING = DescriptiveEnum(2, "Sequencing", description="🧬")
    FINISHED = DescriptiveEnum(3, "Finished", description="✅")
    ARCHIVED = DescriptiveEnum(4, "Archived", description="🗃️")
    FAILED = DescriptiveEnum(5, "Failed", description="❌")


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
    INDEX_I7 = DescriptiveEnum(5, "Index I7")
    INDEX_I5 = DescriptiveEnum(6, "Index I5")