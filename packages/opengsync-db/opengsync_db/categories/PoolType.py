from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False)
class PoolTypeEnum(DBEnum):
    identifier: str

    @property
    def select_name(self) -> str:
        return self.identifier


class PoolType(ExtendedEnum[PoolTypeEnum], enum_type=PoolTypeEnum):
    CUSTOM = PoolTypeEnum(0, "Custom", "C")
    EXTERNAL = PoolTypeEnum(1, "External", "E")
    INTERNAL = PoolTypeEnum(2, "Internal", "I")