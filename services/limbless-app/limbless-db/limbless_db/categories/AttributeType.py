from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class AttributeTypeEnum(DBEnum):
    label: str


class AttributeType(ExtendedEnum[AttributeTypeEnum], enum_type=AttributeTypeEnum):
    CUSTOM = AttributeTypeEnum(0, "Custom", "custom")
    SEX = AttributeTypeEnum(1, "Sex", "sex")
    PHENOTYPE = AttributeTypeEnum(2, "Phenotype", "phenotype")
    GENOTYPE = AttributeTypeEnum(2, "Genotype", "genotype")
    CELL_TYPE = AttributeTypeEnum(3, "Cell Type", "cell_type")
    CONDITION = AttributeTypeEnum(4, "Condition", "condition")
    AGE = AttributeTypeEnum(5, "Age", "age")
    TISSUE = AttributeTypeEnum(6, "Tissue", "tissue")
    DISEASE = AttributeTypeEnum(7, "Disease", "disease")

    @classmethod
    def get_attribute_by_label(cls, label: str) -> AttributeTypeEnum:
        label = label.lower().strip().replace(" ", "_")
        for attribute in cls.as_list():
            if attribute.label == label:
                return attribute
            
        return cls.CUSTOM
