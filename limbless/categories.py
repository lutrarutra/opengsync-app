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
    SC_RNA = DescriptiveEnum(1, "single-cell RNA-Seq")
    SN_RNA = DescriptiveEnum(2, "single-nucleus RNA-Seq")
    SC_ATAC = DescriptiveEnum(3, "single-cell ATAC-Seq")
    SC_MULTIOME = DescriptiveEnum(4, "single-cell Multiome")


class OrganismCategory(Enum, metaclass=ExtendedEnumMeta):
    UNCLASSIFIED = DescriptiveEnum(0, "Unclassified")
    ARCHAEA = DescriptiveEnum(1, "Archaea")
    BACTERIA = DescriptiveEnum(2, "Bacteria")
    EUKARYOTA = DescriptiveEnum(3, "Eukaryota")
    VIRUSES = DescriptiveEnum(4, "Viruses")
    OTHER = DescriptiveEnum(5, "Other")


class AccessType(Enum, metaclass=ExtendedEnumMeta):
    WRITE = DescriptiveEnum(1, "Write")
    READ = DescriptiveEnum(2, "Read")


class SeqRequestStatus(Enum, metaclass=ExtendedEnumMeta):
    CREATED = DescriptiveEnum(0, "Created")
    SUBMITTED = DescriptiveEnum(1, "Submitted")
    FINISHED = DescriptiveEnum(2, "Finished")