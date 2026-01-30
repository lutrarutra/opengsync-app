from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False, frozen=True)
class FeatureTypeEnum(DBEnum):
    label: str
    abbreviation: str
    modality: str


class FeatureType(ExtendedEnum):
    label: str
    abbreviation: str
    modality: str
    CUSTOM = FeatureTypeEnum(0, "Custom", "Custom", "Custom")
    CMO = FeatureTypeEnum(1, "Cell Multiplexing Oligo", "CMO", "Multiplexing Capture")
    ANTIBODY = FeatureTypeEnum(2, "Cell Surface Protein Capture", "ABC", "Antibody Capture")
    CRISPR_CAPTURE = FeatureTypeEnum(3, "CRISPR Capture", "CRISPR", "CRISPR Capture")
    GENE_CAPTURE = FeatureTypeEnum(4, "Gene Capture", "GENE", "Gene Capture")
    PRIMER_CAPTURE = FeatureTypeEnum(5, "Primer Capture", "PRIMER", "Primer Capture")