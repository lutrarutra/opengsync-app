from typing import Generic, Literal, TypeVar, overload

from .BaseInputField import BaseInputField

_DataT = TypeVar("_DataT", int, int | None, str, str | None, covariant=True)


class SelectableInputField(BaseInputField, Generic[_DataT]):
    data: _DataT

    @overload
    def __init__(
        self: "SelectableInputField[int]",
        label: str,
        options: list[tuple[int, str]],
        *,
        default: int | None = None,
        description: str | None = None,
        placeholder: str | None = None,
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
        placeholder: str | None = None,
        required: Literal[False],
        hidden: bool = False,
        read_only: bool = False,
    ) -> None: ...

    @overload
    def __init__(
        self: "SelectableInputField[str]",
        label: str,
        options: list[tuple[str, str]],
        *,
        default: str | None = None,
        description: str | None = None,
        placeholder: str | None = None,
        required: Literal[True] = True,
        hidden: bool = False,
        read_only: bool = False,
    ) -> None: ...

    @overload
    def __init__(
        self: "SelectableInputField[str | None]",
        label: str,
        options: list[tuple[str, str]],
        *,
        default: str | None = None,
        description: str | None = None,
        placeholder: str | None = None,
        required: Literal[False],
        hidden: bool = False,
        read_only: bool = False,
    ) -> None: ...

    def __init__(
        self,
        label: str,
        options: list[tuple[int, str]] | list[tuple[str, str]],
        *,
        default: int | str | None = None,
        description: str | None = None,
        placeholder: str | None = None,
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
        self.placeholder = placeholder or f"Select {label} ({'Required' if required else 'Optional'})"
        self.set_options(options)
        self._mapping = dict(options)

    def set_options(self, options: list[tuple[int, str]] | list[tuple[str, str]]) -> None:
        """Set the options for the selectable input field."""
        self.options = options
        if self.default is None:
            self.options = [("", self.placeholder)] + options  # type: ignore
        self._mapping = dict(options)

    @property
    def value(self) -> str | None:
        """Get the string representation of the selected value"""
        if self.data is None:
            return None
        return self._mapping[self.data]
