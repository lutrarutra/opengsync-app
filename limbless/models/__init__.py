from enum import Enum

from typing import Union

from .Job import Job, JobStatus
from .Project import Project
from .Sample import Sample
from .Run import Run
from .User import User
from .Experiment import Experiment
from .Library import Library
from .Organism import Organism
from .Links import LibrarySampleLink, RunLibraryLink, ProjectUserLink

class ProjectRole(Enum):
    OWNER = 1
    CONTRIBUTOR = 2
    VIEWER = 3

    def __eq__(self, other: Union["ProjectRole", int]):
        if isinstance(other, ProjectRole):
            other = other.value
        return self.value == other

    @staticmethod
    def is_valid(role: Union["ProjectRole", int]):
        if isinstance(role, ProjectRole):
            role = role.value
        return role in [val.value for val in ProjectRole.__members__.values()]

class UserRole(Enum):
    ADMIN = 1
    BIOINFORMATICIAN = 2
    TECHNICIAN = 3
    CLIENT = 4

    def __eq__(self, other: Union["UserRole", int]):
        if isinstance(other, UserRole):
            other = other.value
        return self.value == other

    @staticmethod
    def is_valid(role: Union["UserRole", int]):
        if isinstance(role, UserRole):
            role = role.value
        return role in [val.value for val in UserRole.__members__.values()]

class LibraryType(EnumType):
    TRANSCRIPTOME = LibraryType.create(0, "Transcriptome", "")
    TRANSCRIPTOME_NUCLEI = LibraryType.create(1, "Transcriptome Nuclei", "")
    CUSTOM_BARCODED_FEATURE = LibraryType.create(2, "Custom Barcoded Feature", "")
    ANTIBODY_QUANTIFICATION = LibraryType.create(3, "Antibody Quantification", "")
    VISIUM = LibraryType.create(4, "Visium", "")
    CHROMATIN = LibraryType.create(5, "Chromatin", "")

# class LibraryType(Enum):
#     TRANSCRIPTOME = "Transcriptome"
#     TRANSCRIPTOME_NUCLEI = "Transcriptome Nuclei"
#     CUSTOM_BARCODED_FEATURE = "Custom Barcoded Feature"
#     ANTIBODY_QUANTIFICATION = "Antibody Quantification"
#     ANTIBODY_QUANTIFICATION_CITE = "Antibody Quantification CITE"
#     CRISPR_GUIDE = "CRISPR Guide"
#     CRISPR_GUIDE_SINGLE_INDEX = "CRISPR Guide SINGLE_INDEX"
#     TCR = "TCR"
#     CHROMATIN = "Chromatin"
#     VISIUM = "Visium"
#     MULTIOME_ATAC_AS_ATAC = "Multiome ATAC as ATAC"
#     MULTIOME_GEX = "Multiome GEX"
#     MULTIOME_ATAC = "Multiome ATAC"
#     CUSTOM = "Custom"

    def __eq__(self, other: Union["LibraryType", str]):
        if isinstance(other, LibraryType):
            other = other.value
        return self.value == other

    @staticmethod
    def is_valid(library_type: Union["LibraryType", str]):
        if isinstance(library_type, LibraryType):
            return True
        return library_type in [val.value for val in LibraryType.__members__.values()]
    
    @staticmethod
    def to_tuple():
        return [(val.value, val.name) for val in LibraryType.__members__.values()]
    
class OrganismCategory(Enum):
    OTHER = 0
    ARCHAEA = 1
    BACTERIA = 2
    EUKARYOTA = 3
    VIRUSES = 4
    UNCLASSIFIED = 5

    def __eq__(self, other: Union["OrganismCategory", str]):
        if isinstance(other, OrganismCategory):
            other = other.value
        return self.value == other

    @staticmethod
    def is_valid(organism_type: Union["OrganismCategory", str]):
        if isinstance(organism_type, OrganismCategory):
            organism_type = organism_type.value
        return organism_type in [val.value for val in OrganismCategory.__members__.values()]
    
    @staticmethod
    def to_tuple():
        return [(val.value, val.name) for val in OrganismCategory.__members__.values()]
    
# TODO: Enumerate library types
# LIBRARY_TYPES = [
#     ("Transcriptome", "Transcriptome"),
#     ("Custom_Barcoded_Feature", "Custom Barcoded Feature"),
#     ("Antibody_Quantification", "Antibody Quantification"),
#     ("Antibody_Quantification_CITE", "Antibody Quantification CITE"),
#     ("CRISPR_Guide", "CRISPR Guide"),
#     ("CRISPR_Guide_SINGLE_INDEX", "CRISPR Guide SINGLE_INDEX"),
#     ("TCR", "TCR"),
#     ("Chromatin", "Chromatin"),
#     ("VISIUM", "Visium"),
#     ("Multiome_ATAC_AS_ATAC", "Multiome ATAC as ATAC"),
#     ("Multiome_GEX", "Multiome GEX"),
#     ("Multiome_ATAC", "Multiome ATAC"),
#     ("Transcriptome_nuclei", "Transcriptome Nuclei"),
#     ("Custom", "Custom"),
# ]