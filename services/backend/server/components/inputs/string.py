from typing import Any, Annotated, Generic, Literal, TypeVar, overload
from .InputField import InputField

from pydantic import EmailStr, StringConstraints

_DataT = TypeVar("_DataT", str, str | None, covariant=True)


class StringInputField(InputField, Generic[_DataT]):
    data: _DataT

    @overload
    def __init__(
        self: "StringInputField[str]",
        label: str,
        *,
        template: str | None = None,
        required: Literal[True] = True,
        placeholder: str | None = None,
        max_length: int | None = None,
        min_length: int | None = None,
        description: str | None = None,
        default: str | None = None,
        autocomplete: str | None = None,
        pydantic_type: Any = None,
        type: str = "text",
        hidden: bool = False,
        read_only: bool = False,
    ) -> None: ...

    @overload
    def __init__(
        self: "StringInputField[str | None]",
        label: str,
        *,
        template: str | None = None,
        required: Literal[False],
        placeholder: str | None = None,
        max_length: int | None = None,
        min_length: int | None = None,
        description: str | None = None,
        default: str | None = None,
        autocomplete: str | None = None,
        pydantic_type: Any = None,
        type: str = "text",
        hidden: bool = False,
        read_only: bool = False,
    ) -> None: ...

    @overload
    def __init__(
        self: "StringInputField[str | None]",
        label: str,
        *,
        template: str | None = None,
        required: bool,
        placeholder: str | None = None,
        max_length: int | None = None,
        min_length: int | None = None,
        description: str | None = None,
        default: str | None = None,
        autocomplete: str | None = None,
        pydantic_type: Any = None,
        type: str = "text",
        hidden: bool = False,
        read_only: bool = False,
    ) -> None: ...

    def __init__(
        self, label: str,
        template: str | None = None,
        placeholder: str | None = None,
        max_length: int | None = None,
        min_length: int | None = None,
        description: str | None = None,
        default: str | None = None,
        autocomplete: str | None = None,
        pydantic_type: Any = None,
        required: bool = True,
        type: str = "text",
        hidden: bool = False,
        read_only: bool = False,
    ):
        super().__init__(
            name=label.lower().replace(" ", "_"),
            label=label,
            template=template or "components/inputs/string.html",
            default=default,
            pydantic_type=pydantic_type or Annotated[str, StringConstraints(max_length=max_length, min_length=min_length)],
            type=type,
            description=description,
            required=required,
            hidden=hidden,
            read_only=read_only
        )
        self.placeholder = placeholder
        self.autocomplete = autocomplete


class EmailInputField(StringInputField[_DataT]):
    @overload
    def __init__(
        self: "EmailInputField[str]",
        label: str,
        *,
        required: Literal[True] = True,
        placeholder: str | None = None,
        max_length: int | None = None,
        min_length: int | None = None,
        description: str | None = None,
        default: str | None = None,
        autocomplete: str | None = "email",
        hidden: bool = False,
        read_only: bool = False,
    ) -> None: ...

    @overload
    def __init__(
        self: "EmailInputField[str | None]",
        label: str,
        *,
        required: Literal[False],
        placeholder: str | None = None,
        max_length: int | None = None,
        min_length: int | None = None,
        description: str | None = None,
        default: str | None = None,
        autocomplete: str | None = "email",
        hidden: bool = False,
        read_only: bool = False,
    ) -> None: ...

    @overload
    def __init__(
        self: "EmailInputField[str | None]",
        label: str,
        *,
        required: bool,
        placeholder: str | None = None,
        max_length: int | None = None,
        min_length: int | None = None,
        description: str | None = None,
        default: str | None = None,
        autocomplete: str | None = "email",
        hidden: bool = False,
        read_only: bool = False,
    ) -> None: ...

    def __init__(
        self, label: str,
        placeholder: str | None = None,
        max_length: int | None = None,
        min_length: int | None = None,
        description: str | None = None,
        default: str | None = None,
        autocomplete: str | None = "email",
        required: bool = True,
        hidden: bool = False,
        read_only: bool = False,
    ):
        super().__init__(
            label=label,
            required=required,
            placeholder=placeholder,
            description=description,
            default=default,
            autocomplete=autocomplete,
            pydantic_type=Annotated[str, EmailStr, StringConstraints(max_length=max_length, min_length=min_length)],
            type="email",
            hidden=hidden,
            read_only=read_only,
        )


class PasswordInputField(StringInputField[_DataT]):
    @overload
    def __init__(
        self: "PasswordInputField[str]",
        label: str,
        *,
        required: Literal[True] = True,
        placeholder: str | None = None,
        max_length: int | None = None,
        min_length: int | None = None,
        description: str | None = None,
        default: str | None = None,
        autocomplete: str | None = "current-password",
        hidden: bool = False,
        read_only: bool = False,
    ) -> None: ...

    @overload
    def __init__(
        self: "PasswordInputField[str | None]",
        label: str,
        *,
        required: Literal[False],
        placeholder: str | None = None,
        max_length: int | None = None,
        min_length: int | None = None,
        description: str | None = None,
        default: str | None = None,
        autocomplete: str | None = "current-password",
        hidden: bool = False,
        read_only: bool = False,
    ) -> None: ...

    @overload
    def __init__(
        self: "PasswordInputField[str | None]",
        label: str,
        *,
        required: bool,
        placeholder: str | None = None,
        max_length: int | None = None,
        min_length: int | None = None,
        description: str | None = None,
        default: str | None = None,
        autocomplete: str | None = "current-password",
        hidden: bool = False,
        read_only: bool = False,
    ) -> None: ...

    def __init__(
        self, label: str,
        placeholder: str | None = None,
        max_length: int | None = None,
        min_length: int | None = None,
        description: str | None = None,
        default: str | None = None,
        autocomplete: str | None = "current-password",
        required: bool = True,
        hidden: bool = False,
        read_only: bool = False,
    ):
        super().__init__(
            label=label,
            required=required,
            placeholder=placeholder,
            description=description,
            default=default,
            autocomplete=autocomplete,
            pydantic_type=Annotated[str, StringConstraints(max_length=max_length, min_length=min_length)],
            type="password",
            hidden=hidden,
            read_only=read_only,
        )


class TextAreaInputField(StringInputField[_DataT]):
    @overload
    def __init__(
        self: "TextAreaInputField[str]",
        label: str,
        *,
        required: Literal[True] = True,
        placeholder: str | None = None,
        max_length: int | None = None,
        min_length: int | None = None,
        description: str | None = None,
        default: str | None = None,
        autocomplete: str | None = None,
        hidden: bool = False,
        read_only: bool = False,
    ) -> None: ...

    @overload
    def __init__(
        self: "TextAreaInputField[str | None]",
        label: str,
        *,
        required: Literal[False],
        placeholder: str | None = None,
        max_length: int | None = None,
        min_length: int | None = None,
        description: str | None = None,
        default: str | None = None,
        autocomplete: str | None = None,
        hidden: bool = False,
        read_only: bool = False,
    ) -> None: ...

    @overload
    def __init__(
        self: "TextAreaInputField[str | None]",
        label: str,
        *,
        required: bool,
        placeholder: str | None = None,
        max_length: int | None = None,
        min_length: int | None = None,
        description: str | None = None,
        default: str | None = None,
        autocomplete: str | None = None,
        hidden: bool = False,
        read_only: bool = False,
    ) -> None: ...

    def __init__(
        self, label: str,
        placeholder: str | None = None,
        max_length: int | None = None,
        min_length: int | None = None,
        description: str | None = None,
        default: str | None = None,
        autocomplete: str | None = None,
        required: bool = True,
        hidden: bool = False,
        read_only: bool = False,
    ):
        super().__init__(
            label=label,
            required=required,
            placeholder=placeholder,
            description=description,
            default=default,
            autocomplete=autocomplete,
            template="components/inputs/textarea.html",
            pydantic_type=Annotated[str, StringConstraints(max_length=max_length, min_length=min_length)],
            type="textarea",
            hidden=hidden,
            read_only=read_only,
        )