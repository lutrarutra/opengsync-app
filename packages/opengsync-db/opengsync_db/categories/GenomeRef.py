from typing import Optional
from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False, frozen=True)
class GenomeRefEnum(DBEnum):
    label: str
    organism_latin_name: str | None = None
    organism_tax_id: int | None = None

class GenomeRef(ExtendedEnum):
    label: str
    organism_latin_name: str | None
    organism_tax_id: int | None
    CUSTOM = GenomeRefEnum(0, "Custom")
    HUMAN = GenomeRefEnum(1, "Human", "Homo sapiens", 9606)
    MOUSE = GenomeRefEnum(2, "Mouse", "Mus musculus", 10090)
    YEAST = GenomeRefEnum(3, "Yeast", "Saccharomyces cerevisiae", 4932)
    ECOLI = GenomeRefEnum(4, "E. Coli", "Escherichia coli", 562)
    PIG = GenomeRefEnum(5, "Pig", "Sus scrofa", 9823)
    COVID = GenomeRefEnum(6, "Covid", "SARS-CoV-2", 2697049)

    @property
    def display_name(self) -> str:
        return f"{self.label}" + (f" ({self.organism_latin_name})" if self.organism_latin_name is not None else "")
