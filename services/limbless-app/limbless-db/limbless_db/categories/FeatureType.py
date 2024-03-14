from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class FeatureTypeEnum(DBEnum):
    abbreviation: str


class FeatureType(ExtendedEnum[FeatureTypeEnum], enum_type=FeatureTypeEnum):
    CUSTOM = FeatureTypeEnum(0, "Custom", "Custom")
    CMO = FeatureTypeEnum(1, "Cell Multiplexing Oligo", "CMO")
    ANTIBODY = FeatureTypeEnum(2, "Antibody", "ABC")
    CRISPR_CAPTURE = FeatureTypeEnum(3, "CRISPR Capture", "CRISPR")
    GENE_CAPTURE = FeatureTypeEnum(4, "Gene Capture", "GENE")
    PRIMER_CAPTURE = FeatureTypeEnum(5, "Primer Capture", "PRIMER")