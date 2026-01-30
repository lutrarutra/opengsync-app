from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False, frozen=True)
class ReadTypeEnum(DBEnum):
    label: str
    icon: str


class ReadType(ExtendedEnum):
    label: str
    icon: str
    OTHER = ReadTypeEnum(0, "Other", "⚙️")
    SINGLE_END = ReadTypeEnum(1, "Single-end", "➡️")
    PAIRED_END = ReadTypeEnum(2, "Paired-end", "🔁")