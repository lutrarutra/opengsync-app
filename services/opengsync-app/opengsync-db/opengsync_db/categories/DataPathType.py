from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False)
class DataPathTypeEnum(DBEnum):
    extensions: list[str] | None = None


class DataPathType(ExtendedEnum[DataPathTypeEnum], enum_type=DataPathTypeEnum):
    CUSTOM = DataPathTypeEnum(0, "Custom")
    DIRECTORY = DataPathTypeEnum(1, "Directory")
    PDF = DataPathTypeEnum(2, "PDF", ["pdf"])
    TABLE = DataPathTypeEnum(3, "Table", ["tsv", "csv"])
    EXCEL = DataPathTypeEnum(4, "Excel", ["xlsx", "xls"])
    IMAGE = DataPathTypeEnum(5, "Image", ["png", "jpg", "jpeg"])
    HTML = DataPathTypeEnum(6, "HTML", ["html"])