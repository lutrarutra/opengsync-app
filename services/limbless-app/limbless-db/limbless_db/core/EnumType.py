from enum import Enum, EnumMeta
from dataclasses import dataclass

from typing import TypeVar, Tuple, Type

T = TypeVar('T', bound=Enum)


@dataclass
class DescriptiveEnum():
    id: int
    name: str
    description: str | None = None

    def __str__(self) -> str:
        return f"{self.name} ({self.description}) [{self.id}]"


class ExtendedEnumMeta(EnumMeta):
    def as_tuples(cls: Type[T]) -> list[Tuple[int, DescriptiveEnum]]:
        return [(c.value.id, c.value) for c in cls]
    
    def as_selectable(cls: Type[T]) -> list[Tuple[int, str]]:
        return [(c.value.id, c.value.name + (f" ({c.value.description})" if c.value.description else "")) for c in cls]
    
    def names(cls: Type[T]) -> list[str]:
        return [c.value.name for c in cls]
    
    def descriptions(cls: Type[T]) -> list[str]:
        return [c.value.description for c in cls]

    def get(cls: Type[T], id: int) -> T:
        for member in cls:
            if member.value.id == id:
                return member
        raise ValueError(f"No member with id '{id}' (type: {type(id)}) found.")

    def as_dict(cls: Type[T]) -> dict[int, T]:
        return {c.value.id: c.value for c in cls}

    def is_valid(cls: Type[T], id: int) -> bool:
        for member in cls:
            if member.value.id == id:
                return True
        return False
