from typing import Any, Annotated
from .InputField import InputField

from pydantic import EmailStr, StringConstraints

class StringInputField(InputField):
    data: str | None = None
    
    def __init__(
        self, label: str,
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
            template="components/inputs/string.html",
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


class EmailInputField(StringInputField):
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
            default=default,
            pydantic_type=Annotated[str, EmailStr, StringConstraints(max_length=max_length, min_length=min_length)],
            autocomplete=autocomplete,
            placeholder=placeholder,
            required=required,
            description=description,
            hidden=hidden,
            read_only=read_only,
            type="email"
        )


class PasswordInputField(StringInputField):
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
            default=default,
            pydantic_type=Annotated[str, StringConstraints(max_length=max_length, min_length=min_length)],
            autocomplete=autocomplete,
            placeholder=placeholder,
            type="password",
            description=description,
            required=required,
            hidden=hidden,
            read_only=read_only,
        )


class TextAreaInputField(StringInputField):
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
            default=default,
            pydantic_type=Annotated[str, StringConstraints(max_length=max_length, min_length=min_length)],
            autocomplete=autocomplete,
            placeholder=placeholder,
            type="textarea",
            description=description,
            required=required,
            hidden=hidden,
            read_only=read_only
        )