from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum

@dataclass(eq=False, frozen=True)
class AttributeTypeEnum(DBEnum):
    label: str


class AttributeType(ExtendedEnum):
    label: str
    
    CUSTOM = AttributeTypeEnum(0, "custom")
    SEX = AttributeTypeEnum(1, "sex")
    # PHENOTYPE = AttributeTypeEnum(2, "Phenotype", "phenotype")
    GENOTYPE = AttributeTypeEnum(2, "genotype")
    CELL_TYPE = AttributeTypeEnum(3, "cell_type")
    CONDITION = AttributeTypeEnum(4, "condition")
    AGE = AttributeTypeEnum(5, "age")
    TISSUE = AttributeTypeEnum(6, "tissue")
    DISEASE = AttributeTypeEnum(7, "disease")

    @classmethod
    def get_attribute_by_label(cls, label: str) -> "AttributeType":
        label = label.lower().strip().replace(" ", "_")
        for attribute in cls.as_list():
            if attribute.label == label:
                return attribute
            
        return cls.CUSTOM