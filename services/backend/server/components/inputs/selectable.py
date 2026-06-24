from typing import Generic, Literal, TypeVar, overload

from .BaseInputField import BaseInputField

T_int = TypeVar("T_int", int, int | None, covariant=True)


class SelectableInputField(BaseInputField, Generic[T_int]):
    data: T_int

    @overload
    def __init__(
        self: "SelectableInputField[int]",
        label: str,
        options: list[tuple[int, str]],
        *,
        default: int | None = None,
        description: str | None = None,
        required: Literal[True] = True,
        hidden: bool = False,
        read_only: bool = False,
    ) -> None: ...

    @overload
    def __init__(
        self: "SelectableInputField[int | None]",
        label: str,
        options: list[tuple[int, str]],
        *,
        default: int | None = None,
        description: str | None = None,
        required: Literal[False],
        hidden: bool = False,
        read_only: bool = False,
    ) -> None: ...

    def __init__(
        self,
        label: str,
        options: list[tuple[int, str]],
        *,
        default: int | None = None,
        description: str | None = None,
        required: bool = True,
        hidden: bool = False,
        read_only: bool = False,
    ):
        pydantic_type = type(options[0][0]) if options else str
        super().__init__(
            label=label,
            template="components/inputs/selectable.html",
            default=default,
            pydantic_type=pydantic_type,
            type="select",
            required=required,
            description=description,
            hidden=hidden,
            read_only=read_only,
        )
        self.options: list[tuple[int, str]] = options
