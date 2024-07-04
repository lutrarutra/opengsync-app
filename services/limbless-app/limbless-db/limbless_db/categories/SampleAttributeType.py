from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class SampleAttributeTypeEnum(DBEnum):
    label: str


class SampleAttributeType(ExtendedEnum[SampleAttributeTypeEnum], enum_type=SampleAttributeTypeEnum):
    CUSTOM = SampleAttributeTypeEnum(0, "Custom", "custom")
    SEX = SampleAttributeTypeEnum(1, "Sex", "sex")
    PHENOTYPE = SampleAttributeTypeEnum(2, "Phenotype", "phenotype")
    CELL_TYPE = SampleAttributeTypeEnum(3, "Cell Type", "cell_type")
    CONDITION = SampleAttributeTypeEnum(4, "Condition", "condition")
