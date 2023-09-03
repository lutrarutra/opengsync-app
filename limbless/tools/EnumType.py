from dataclasses import dataclass
from typing import Optional, Union
from abc import ABC

@dataclass
class DescriptiveEnum:
    __id: int
    name: str
    description: Optional[str]
    __enum_type: str

    __types__ = dict()

    def __init__(self, enum_type: str, _id: int, name: str, description: Optional[str]=None):
        if enum_type not in self.__types__.keys():
            self.__types__[enum_type] = dict()

        if id in self.__types__[enum_type].keys():
            raise Exception(f"Library type with id '{id}' already exists.")

        self.__id = _id
        self.name = name
        self.description = description
        self.__enum_type = enum_type

        self.__types__[enum_type][self.__id] = self

    @property
    def id(self) -> int:
        return self.__id

    @classmethod
    def values(cls, enum_type: str) -> list["DescriptiveEnum"]:
        if enum_type not in cls.__types__.keys():
            raise Exception(f"No DescriptiveEnums with type '{enum_type}' found.")

        return list(cls.__types__[enum_type].values())

    @classmethod
    def names(cls, enum_type: str) -> list[str]:
        return [_type.name for _type in cls.values(enum_type)]

    @classmethod
    def as_tuples(cls, enum_type: str) -> tuple[int, str]:
        if enum_type not in cls.__types__.keys():
            raise Exception(f"No DescriptiveEnums with type '{enum_type}' found.")

        return [(_type.__id, _type.name) for _type in cls.__types__[enum_type].values()]

    @classmethod
    def as_dict(cls, enum_type: str) -> dict[int, str]:
        return dict(cls.as_tuples(enum_type))

    @classmethod
    def is_valid_id(cls, enum_type: str, _id: int) -> bool:
        return _id in cls.__types__[enum_type].keys()

    def __str__(self):
        return f"{self.__enum_type}(id={self.__id}, name='{self.name}', description='{self.description}')"

    def __repr__(self):
        return f"{self.__enum_type}(id={self.__id}, name='{self.name}')"

class EnumType:
    @classmethod
    def get_enum_type(cls):
        return cls.__enum_type__
        
    @classmethod
    def create(cls, _id, name, description=None) -> DescriptiveEnum:
        return DescriptiveEnum(cls.__enum_type__, _id, name, description)

    @classmethod
    def as_tuples(cls) -> tuple[int, str]:
        return DescriptiveEnum.as_tuples(cls.__name__)
    
    @classmethod
    def as_dict(cls) -> dict[int, str]:
        return DescriptiveEnum.as_dict(cls.__name__)

    @classmethod
    def values(cls) -> list[DescriptiveEnum]:
        return DescriptiveEnum.values(cls.__name__)
    
    @classmethod
    def is_valid(cls, _id: Union[DescriptiveEnum, int]) -> bool:
        if isinstance(_id, DescriptiveEnum):
            return True
        return cls.is_valid_id(_id)

    @classmethod
    def is_valid_id(cls, _id: int) -> bool:
        return DescriptiveEnum.is_valid_id(cls.__name__, _id)

    @classmethod
    def is_valid_name(cls, name: str):
        return name in cls.names()

    @classmethod
    def get(cls, id: int):
        if cls.is_valid_id(id):
            return DescriptiveEnum.__types__[cls.__name__][id]

        return None