from typing import Optional
from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class GenomeRefEnum(DBEnum):
    organism_latin_name: str
    organism_tax_id: Optional[int] = None


class GenomeRef(ExtendedEnum[GenomeRefEnum], enum_type=GenomeRefEnum):
    CUSTOM = GenomeRefEnum(0, "Custom", "Custom")
    HUMAN = GenomeRefEnum(1, "Human", "Homo sapiens", 9606)
    MOUSE = GenomeRefEnum(2, "Mouse", "Mus musculus", 10090)
    YEAST = GenomeRefEnum(3, "Yeast", "Saccharomyces cerevisiae", 4932)
    ECOLI = GenomeRefEnum(4, "E. Coli", "Escherichia coli", 562)
    PIG = GenomeRefEnum(5, "Pig", "Sus scrofa", 9823)