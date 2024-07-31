from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class PoolTypeEnum(DBEnum):
    pass


class PoolType(ExtendedEnum[PoolTypeEnum], enum_type=PoolTypeEnum):
    CUSTOM = PoolTypeEnum(0, "Custom")
    EXTERNAL = PoolTypeEnum(1, "External")
    INTERNAL = PoolTypeEnum(2, "Internal")