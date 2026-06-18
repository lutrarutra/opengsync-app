from typing import TypeVar, Generic, Literal, overload

from .InputField import InputField

T_int = TypeVar("T_int", int, int | None, covariant=True)

class SelectableInputField(InputField, Generic[T_int]):
    data: T_int

    @overload
    def __init__(
        self: "SelectableInputField[T_int]",  # type: ignore[override]
        label: str,
        options: list[tuple[T_int, str]],
        *,
        required: Literal[True] = True,
        default: T_int | None = None,
        description: str | None = None,
        hidden: bool = False,
        read_only: bool = False,
    ) -> None: ...

    @overload
    def __init__(
        self: "SelectableInputField[T_int | None]",  # type: ignore[override]
        label: str,
        options: list[tuple[T_int, str]],
        *,
        required: Literal[False],
        default: T_int | None = None,
        description: str | None = None,
        hidden: bool = False,
        read_only: bool = False,
    ) -> None: ...

    @overload
    def __init__(
        self: "SelectableInputField[T_int | None]",  # type: ignore[override]
        label: str,
        options: list[tuple[T_int, str]],
        *,
        required: bool,
        default: T_int | None = None,
        description: str | None = None,
        hidden: bool = False,
        read_only: bool = False,
    ) -> None: ...

    def __init__(
        self,
        label: str,
        options: list[tuple[T_int, str]],
        default: T_int | None = None,
        description: str | None = None,
        required: bool = True,
        hidden: bool = False,
        read_only: bool = False,
    ):
        pydantic_type = type(options[0][0]) if options else str
        super().__init__(
            name=label.lower().replace(" ", "_"),
            label=label,
            template="components/inputs/selectable.html",
            default=default,
            pydantic_type=pydantic_type,
            type="select",
            required=required,
            description=description,
            hidden=hidden,
            read_only=read_only
        )
        self.options: list[tuple[T_int, str]] = options
