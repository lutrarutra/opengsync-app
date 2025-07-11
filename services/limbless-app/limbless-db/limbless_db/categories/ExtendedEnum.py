from dataclasses import dataclass
from typing import TypeVar, Generic, Type
from collections import OrderedDict


@dataclass(eq=False)
class DBEnum():
    id: int
    name: str

    def __post_init__(self) -> None:
        self.__class__.__hash__ = DBEnum.__hash__  # type: ignore

    def __str__(self) -> str:
        return f"{self.display_name} [{self.id}]"
    
    @property
    def display_name(self) -> str:
        return self.name
    
    @property
    def select_name(self) -> str:
        return str(self.id)
    
    def __lt__(self, other) -> bool:
        return self.id < other.id
    
    def __gt__(self, other) -> bool:
        return self.id > other.id
    
    def __ge__(self, other) -> bool:
        return self.id >= other.id
    
    def __le__(self, other) -> bool:
        return self.id <= other.id

    def __eq__(self, other) -> bool:
        if not isinstance(other, DBEnum):
            return False
        return self.id == other.id and self.name == other.name
    
    def __hash__(self) -> int:
        return hash(self.id)
    
    
T = TypeVar("T")
    
    
class ExtendedEnum(Generic[T]):
    __enums__: dict[str, dict[int, T]] = {}

    def __init_subclass__(cls, enum_type: Type[DBEnum]) -> None:
        for var in dir(cls):
            if isinstance(getattr(cls, var), enum_type):
                if cls.__name__ not in cls.__enums__:  # type: ignore
                    cls.__enums__[cls.__name__] = {}  # type: ignore
                cls.__enums__[cls.__name__][getattr(cls, var).id] = getattr(cls, var)  # type: ignore

        cls.__enums__[cls.__name__] = OrderedDict(sorted(cls.__enums__[cls.__name__].items()))  # type: ignore
        return super().__init_subclass__()
    
    @classmethod
    def get(cls, id: int) -> T:
        try:
            return cls.__enums__[cls.__name__][id]  # type: ignore
        except KeyError:
            raise ValueError(f"Invalid {cls.__name__} id: {id}")
    
    @classmethod
    def as_dict(cls) -> dict[int, T]:
        return cls.__enums__[cls.__name__]  # type: ignore
    
    @classmethod
    def as_list(cls) -> list[T]:
        return list(cls.__enums__[cls.__name__].values())  # type: ignore
    
    @classmethod
    def as_tuples(cls) -> list[tuple[int, T]]:
        return [(e.id, e) for e in cls.as_list()]  # type: ignore
        
    @classmethod
    def as_selectable(cls) -> list[tuple[int, str]]:
        return [(e.id, e.display_name) for e in cls.as_list()]  # type: ignore

    @classmethod
    def names(cls) -> list[str]:
        return [e.display_name for e in cls.as_list()]  # type: ignore