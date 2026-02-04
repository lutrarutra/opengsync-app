from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False, frozen=True)
class PoolTypeEnum(DBEnum):
    label: str
    identifier: str


class PoolType(ExtendedEnum):
    label: str
    identifier: str
    CUSTOM = PoolTypeEnum(0, "Custom", "C")
    EXTERNAL = PoolTypeEnum(1, "External", "E")
    INTERNAL = PoolTypeEnum(2, "Internal", "I")

    @property
    def select_name(self) -> str:
        return self.identifier