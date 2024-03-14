from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class ReadTypeEnum(DBEnum):
    icon: str


class ReadType(ExtendedEnum[ReadTypeEnum], enum_type=ReadTypeEnum):
    OTHER = ReadTypeEnum(0, "Other", "⚙️")
    SINGLE_END = ReadTypeEnum(1, "Single-end", "➡️")
    PAIRED_END = ReadTypeEnum(2, "Paired-end", "🔁")