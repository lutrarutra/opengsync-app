from typing import TypeVar, Generic

from .InputField import InputField

T = TypeVar("T")

class SelectableInputField(InputField, Generic[T]):
    def __init__(
        self,
        label: str,
        options: list[tuple[T, str]],
        default: T | None = None,
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
        self.options: list[tuple[T, str]] = options
    