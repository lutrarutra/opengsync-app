from typing import Optional
from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False)
class GenomeRefEnum(DBEnum):
    assembly: Optional[str] = None
    organism_latin_name: Optional[str] = None
    organism_tax_id: int | None = None

    @property
    def display_name(self) -> str:
        return f"{self.name}" + (f" ({self.assembly})" if self.assembly is not None else "")


class GenomeRef(ExtendedEnum[GenomeRefEnum], enum_type=GenomeRefEnum):
    CUSTOM = GenomeRefEnum(0, "Custom")
    HUMAN = GenomeRefEnum(1, "Human", "Homo sapiens", "Homo sapiens", 9606)
    MOUSE = GenomeRefEnum(2, "Mouse", "Mus musculus", "Mus musculus", 10090)
    YEAST = GenomeRefEnum(3, "Yeast", "Saccharomyces cerevisiae", "Saccharomyces cerevisiae", 4932)
    ECOLI = GenomeRefEnum(4, "E. Coli", "Escherichia coli", "Escherichia coli", 562)
    PIG = GenomeRefEnum(5, "Pig", "Sus scrofa", "Sus scrofa", 9823)
    COVID = GenomeRefEnum(6, "Covid", "SARS-CoV-2", None, 2697049)