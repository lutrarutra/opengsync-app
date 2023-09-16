from enum import Enum, EnumMeta
from dataclasses import dataclass

from typing import TypeVar, Tuple, Type, Union

T = TypeVar('T', bound=Enum)


@dataclass
class DescriptiveEnum():
    id: int
    name: str
    description: str | None = None

class ExtendedEnumMeta(EnumMeta):
    def as_tuples(cls: Type[T]) -> list[Tuple[int, DescriptiveEnum]]:
        return [(c.value.id, c.value) for c in cls]
    
    def as_selectable(cls: Type[T]) -> list[Tuple[int, str]]:
        return [(c.value.id, c.value.name) for c in cls]

    def get(cls: Type[T], id: int) -> T:
        for member in cls:
            if member.value.id == id:
                return member
        raise ValueError(f"No member with id {id} found.")

    def as_dict(cls: Type[T]) -> dict[int, DescriptiveEnum]:
        return {c.value.id: c.value for c in cls}

    def is_valid(cls: Type[T], id: int) -> bool:
        for member in cls:
            if member.value.id == id:
                return True
        return False
