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
    HUMAN = GenomeRefEnum(1, "Human", "GRCh38", "Homo sapiens", 9606)
    MOUSE = GenomeRefEnum(2, "Mouse", "GRCm38", "Mus musculus", 10090)
    YEAST = GenomeRefEnum(3, "Yeast", "R64", "Saccharomyces cerevisiae", 4932)
    ECOLI = GenomeRefEnum(4, "E. Coli", "ASM584v2", "Escherichia coli", 562)
    PIG = GenomeRefEnum(5, "Pig", "susScr11", "Sus scrofa", 9823)
    COVID = GenomeRefEnum(6, "Covid", "SARS-CoV-2", None, 2697049)