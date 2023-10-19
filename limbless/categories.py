from enum import Enum
from .tools.EnumType import ExtendedEnumMeta, DescriptiveEnum


class UserResourceRelation(Enum, metaclass=ExtendedEnumMeta):
    OWNER = DescriptiveEnum(1, "Owner")
    CONTRIBUTOR = DescriptiveEnum(2, "Contributor")
    VIEWER = DescriptiveEnum(3, "Viewer")


class UserRole(Enum, metaclass=ExtendedEnumMeta):
    ADMIN = DescriptiveEnum(1, "Admin")
    BIOINFORMATICIAN = DescriptiveEnum(2, "Bioinformatician")
    TECHNICIAN = DescriptiveEnum(3, "Technician")
    CLIENT = DescriptiveEnum(4, "Client")


class LibraryType(Enum, metaclass=ExtendedEnumMeta):
    SC_RNA = DescriptiveEnum(1, "Single-cell RNA-Seq")
    SN_RNA = DescriptiveEnum(2, "Single-nucleus RNA-Seq")
    SC_ATAC = DescriptiveEnum(3, "Single-cell ATAC-Seq")
    SC_MULTIOME = DescriptiveEnum(4, "Single-cell Multiome")


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
    CREATED = DescriptiveEnum(0, "Created", description="✍🏼")
    SUBMITTED = DescriptiveEnum(1, "Submitted", description="⏳")
    LIBRARY_PREP = DescriptiveEnum(2, "Library Preparation", description="🧪")
    SEQUENCING = DescriptiveEnum(3, "Sequencing", description="🧬")
    DATA_PROCESSING = DescriptiveEnum(4, "Data Processing", description="👨🏽‍💻")
    FINISHED = DescriptiveEnum(5, "Finished", description="✅")
    ARCHIVED = DescriptiveEnum(6, "Archived", description="🗃️")
    FAILED = DescriptiveEnum(7, "Failed", description="❌")


class ExperimentStatus(Enum, metaclass=ExtendedEnumMeta):
    CREATED = DescriptiveEnum(0, "Created", description="✍🏼")
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
    