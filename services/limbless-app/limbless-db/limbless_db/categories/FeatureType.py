from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class FeatureTypeEnum(DBEnum):
    abbreviation: str
    modality: str


class FeatureType(ExtendedEnum[FeatureTypeEnum], enum_type=FeatureTypeEnum):
    CUSTOM = FeatureTypeEnum(0, "Custom", "Custom", "Custom")
    CMO = FeatureTypeEnum(1, "Cell Multiplexing Oligo", "CMO", "Multiplexing Capture")
    ANTIBODY = FeatureTypeEnum(2, "Antibody", "ABC", "Antibody Capture")
    CRISPR_CAPTURE = FeatureTypeEnum(3, "CRISPR Capture", "CRISPR", "CRISPR Capture")
    GENE_CAPTURE = FeatureTypeEnum(4, "Gene Capture", "GENE", "Gene Capture")
    PRIMER_CAPTURE = FeatureTypeEnum(5, "Primer Capture", "PRIMER", "Primer Capture")