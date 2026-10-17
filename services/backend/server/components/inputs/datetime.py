from datetime import date, datetime
from typing import Annotated, Generic, Literal, TypeVar, overload

from pydantic import Field

from .BaseInputField import BaseInputField

_DateDataT = TypeVar("_DateDataT", date, date | None, covariant=True)
_DateTimeDataT = TypeVar("_DateTimeDataT", datetime, datetime | None, covariant=True)


class DatepickerInputField(BaseInputField, Generic[_DateDataT]):
    data: _DateDataT

    @overload
    def __init__(
        self: "DatepickerInputField[date]",
        label: str,
        *,
        placeholder: str | None = None,
        description: str | None = None,
        default: date | None = None,
        required: Literal[True] = True,
        hidden: bool = False,
        read_only: bool = False,
    ) -> None: ...

    @overload
    def __init__(
        self: "DatepickerInputField[date | None]",
        label: str,
        *,
        placeholder: str | None = None,
        description: str | None = None,
        default: date | None = None,
        required: Literal[False],
        hidden: bool = False,
        read_only: bool = False,
    ) -> None: ...

    def __init__(
        self,
        label: str,
        placeholder: str | None = None,
        description: str | None = None,
        default: date | None = None,
        required: bool = True,
        hidden: bool = False,
        read_only: bool = False,
    ):
        super().__init__(
            label=label,
            template="components/inputs/datepicker.html",
            default=default,
            pydantic_type=Annotated[date, Field(description=description or "")],
            type="date",
            description=description,
            required=required,
            hidden=hidden,
            read_only=read_only,
        )
        self.placeholder = placeholder


class DateTimepickerInputField(BaseInputField, Generic[_DateTimeDataT]):
    data: _DateTimeDataT

    @overload
    def __init__(
        self: "DateTimepickerInputField[datetime]",
        label: str,
        *,
        placeholder: str | None = None,
        description: str | None = None,
        default: datetime | None = None,
        required: Literal[True] = True,
        hidden: bool = False,
        read_only: bool = False,
    ) -> None: ...

    @overload
    def __init__(
        self: "DateTimepickerInputField[datetime | None]",
        label: str,
        *,
        placeholder: str | None = None,
        description: str | None = None,
        default: datetime | None = None,
        required: Literal[False],
        hidden: bool = False,
        read_only: bool = False,
    ) -> None: ...

    def __init__(
        self,
        label: str,
        placeholder: str | None = None,
        description: str | None = None,
        default: datetime | None = None,
        required: bool = True,
        hidden: bool = False,
        read_only: bool = False,
    ):
        super().__init__(
            label=label,
            template="components/inputs/datetimepicker.html",
            default=default,
            pydantic_type=Annotated[datetime, Field(description=description or "")],
            type="datetime-local",
            description=description,
            required=required,
            hidden=hidden,
            read_only=read_only,
        )
        self.placeholder = placeholder