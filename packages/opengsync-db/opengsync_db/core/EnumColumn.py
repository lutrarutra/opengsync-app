from typing import Generic, TypeVar

import sqlalchemy as sa
from sqlalchemy.types import TypeDecorator

from ..categories.ExtendedEnum import ExtendedEnum

E = TypeVar("E", bound=ExtendedEnum)


class EnumColumn(TypeDecorator, Generic[E]):
    impl = sa.SmallInteger
    cache_ok = True

    def __init__(self, enum_class: type[E]):
        super().__init__()
        self.enum_class = enum_class

    def process_bind_param(self, value: E | int | None, dialect) -> int | None:
        if value is None:
            return None
        if isinstance(value, self.enum_class):
            return value.id
        if isinstance(value, int):
            return self.enum_class.get(value).id  # reject unknown ids early
        raise TypeError(
            f"expected {self.enum_class.__name__} or int, got {type(value).__name__}"
        )

    def process_result_value(self, value: int | None, dialect) -> E | None:
        if value is None:
            return None
        return self.enum_class.get(value)

    @property
    def python_type(self) -> type[E]:
        return self.enum_class