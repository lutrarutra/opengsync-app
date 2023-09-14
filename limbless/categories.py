from .tools.EnumType import EnumType


class UserResourceRelation(EnumType):
    EnumType.__enum_type__ = "UserResourceRelation"
    OWNER = EnumType.create(1, "Owner", "")
    CONTRIBUTOR = EnumType.create(2, "Contributor", "")
    VIEWER = EnumType.create(3, "Viewer", "")


class UserRole(EnumType):
    EnumType.__enum_type__ = "UserRole"
    ADMIN = EnumType.create(1, "Admin", "")
    BIOINFORMATICIAN = EnumType.create(2, "Bioinformatician", "")
    TECHNICIAN = EnumType.create(3, "Technician", "")
    CLIENT = EnumType.create(4, "Client", "")


class LibraryType(EnumType):
    EnumType.__enum_type__ = "LibraryType"
    SC_RNA = EnumType.create(1, "single-cell RNA-Seq", "")
    SN_RNA = EnumType.create(2, "single-nucleus RNA-Seq", "")
    SC_ATAC = EnumType.create(3, "single-cell ATAC-Seq", "")
    SC_MULTIOME = EnumType.create(4, "single-cell Multiome", "")


class OrganismCategory(EnumType):
    EnumType.__enum_type__ = "OrganismCategory"
    UNCLASSIFIED = EnumType.create(0, "Unclassified", "")
    ARCHAEA = EnumType.create(1, "Archaea", "")
    BACTERIA = EnumType.create(2, "Bacteria", "")
    EUKARYOTA = EnumType.create(3, "Eukaryota", "")
    VIRUSES = EnumType.create(4, "Viruses", "")
    OTHER = EnumType.create(5, "Other", "")


class AccessType(EnumType):
    EnumType.__enum_type__ = "AccessType"
    WRITE = EnumType.create(1, "Write", "")
    READ = EnumType.create(2, "Read", "")


class SeqRequestStatus(EnumType):
    EnumType.__enum_type__ = "SeqRequestStatus"
    CREATED = EnumType.create(0, "Created", "")
    SUBMITTED = EnumType.create(1, "Submitted", "")
    FINISHED = EnumType.create(2, "Finished", "")
