import enum
import pandas as pd
from dataclasses import dataclass, fields
from typing import Any, TypeVar
T = TypeVar("T", bound="ExtendedEnum")
    
class ExtendedEnum(enum.IntEnum):
    id: int
    
    def __new__(cls, data: Any):
        dataclass_fields = fields(data)
        if not dataclass_fields:
            raise TypeError("ExtendedEnum value must be a dataclass instance")
        value = getattr(data, dataclass_fields[0].name)
        obj = int.__new__(cls, value)
        obj._value_ = value
        for field in dataclass_fields:
            field_name = field.name
            field_value = getattr(data, field_name)
            if field_name == 'name':
                setattr(obj, 'label', field_value.replace("_", " ").title())
            else:
                setattr(obj, field_name, field_value)
        return obj
    
    def __arrow_value__(self):
        return self.id

    @classmethod
    def _missing_(cls, value):
        return cls.as_dict().get(value)  # type: ignore
    
    def __reduce_ex__(self, protocol):
        return int, (self._value_,)

    @classmethod
    def to_categorical(cls, series: pd.Series) -> pd.Series:
        return pd.Categorical(series, categories=list(cls), ordered=True)  # type: ignore

    def __str__(self) -> str:
        return f"{self.__class__.__name__}[{self.name}]"
    __repr__ = __str__

    @property
    def display_name(self) -> str:
        return getattr(self, 'label', self.name.replace("_", " ").title())
    
    @property
    def select_name(self) -> str:
        return f"{self.id}"
    
    def check_type(self, other: Any) -> None:
        if not isinstance(other, ExtendedEnum) and not isinstance(other, int):
            raise TypeError(f"Cannot compare {self.__class__.__name__} with {type(other).__name__}")
        if self.__class__ is not other.__class__ and not isinstance(other, int):
            raise TypeError(f"Cannot compare {self.__class__.__name__} with {other.__class__.__name__}")
    
    def __eq__(self, other: Any) -> bool:
        if pd.isna(other):
            return False
        self.check_type(other)
        return self.id == other.id if isinstance(other, ExtendedEnum) else self.id == other

    def __lt__(self, other: Any) -> bool:
        self.check_type(other)
        return self.id < other.id if isinstance(other, ExtendedEnum) else self.id < other

    def __le__(self, other: Any) -> bool:
        self.check_type(other)
        return self.id <= other.id if isinstance(other, ExtendedEnum) else self.id <= other

    def __gt__(self, other: Any) -> bool:
        self.check_type(other)
        return self.id > other.id if isinstance(other, ExtendedEnum) else self.id > other

    def __ge__(self, other: Any) -> bool:
        self.check_type(other)
        return self.id >= other.id if isinstance(other, ExtendedEnum) else self.id >= other

    @classmethod
    def as_list(cls: type[T]) -> list[T]:
        return list(cls)

    @classmethod
    def as_dict(cls: type[T]) -> dict[int, T]:
        return {item.id: item for item in cls}

    @classmethod
    def as_tuples(cls: type[T]) -> list[tuple[int, T]]:
        return [(item.id, item) for item in cls]
    
    @classmethod
    def names(cls: type[T]) -> list[str]:
        return [item.display_name for item in cls]
    
    @classmethod
    def as_selectable(cls) -> list[tuple[int, str]]:
        return [(item.id, item.display_name) for item in cls]
    
    @classmethod
    def get(cls: type[T], value: Any) -> T:
        if isinstance(value, cls):
            return value
        if isinstance(value, int):
            member = cls._missing_(value)
            if member is not None:
                return member
        raise ValueError(f"{value} is not a valid {cls.__name__}")
    
    def __hash__(self):
        return hash(self.id)
    
    @classmethod
    def map_series(cls: type[T], series: pd.Series, na_action: str | None = "ignore") -> pd.Series:
        return pd.Series([cls.get(val) if pd.notna(val) else None for val in series], dtype="object") if na_action == "ignore" else pd.Series([cls.get(val) for val in series], dtype="object")
        

@dataclass(frozen=True)
class DBEnum:
    id: int