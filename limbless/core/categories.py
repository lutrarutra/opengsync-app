from ..tools.EnumType import EnumType

class ProjectRole(EnumType):
    EnumType.__enum_type__ = "ProjectRole"
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
    TRANSCRIPTOME = EnumType.create(0, "Transcriptome", "")
    TRANSCRIPTOME_NUCLEI = EnumType.create(1, "Transcriptome Nuclei", "")
    CUSTOM_BARCODED_FEATURE = EnumType.create(2, "Custom Barcoded Feature", "")
    ANTIBODY_QUANTIFICATION = EnumType.create(3, "Antibody Quantification", "")
    VISIUM = EnumType.create(4, "Visium", "")
    CHROMATIN = EnumType.create(5, "Chromatin", "")

class OrganismCategory(EnumType):
    EnumType.__enum_type__ = "OrganismCategory"
    UNCLASSIFIED = EnumType.create(0, "Unclassified", "")
    ARCHAEA = EnumType.create(1, "Archaea", "")
    BACTERIA = EnumType.create(2, "Bacteria", "")
    EUKARYOTA = EnumType.create(3, "Eukaryota", "")
    VIRUSES = EnumType.create(4, "Viruses", "")
    OTHER = EnumType.create(5, "Other", "")