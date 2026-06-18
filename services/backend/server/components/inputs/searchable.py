from typing import TypeVar, Generic, Literal, overload

from starlette.datastructures import URL

from .InputField import InputField
from ...core.context import ctx

_T = TypeVar("_T", covariant=True)


class SearchableInputField(InputField, Generic[_T]):
    data: _T

    @overload
    def __init__(
        self: "SearchableInputField[int]",
        label: str,
        *,
        route: str,
        placeholder: str | None = None,
        pydantic_type: type[int] = int,
        default: int | None = None,
        autocomplete: str | None = None,
        type: str = "search",
        hidden: bool = False,
        read_only: bool = False,
    ) -> None: ...

    @overload
    def __init__(
        self: "SearchableInputField[int | None]",
        label: str,
        *,
        route: str,
        placeholder: str | None = None,
        required: Literal[False],
        pydantic_type: type[int] = int,
        default: int | None = None,
        autocomplete: str | None = None,
        type: str = "search",
        hidden: bool = False,
        read_only: bool = False,
    ) -> None: ...

    @overload
    def __init__(
        self: "SearchableInputField[str]",
        label: str,
        *,
        route: str,
        placeholder: str | None = None,
        pydantic_type: type[str],
        default: str | None = None,
        autocomplete: str | None = None,
        type: str = "search",
        hidden: bool = False,
        read_only: bool = False,
    ) -> None: ...

    @overload
    def __init__(
        self: "SearchableInputField[str | None]",
        label: str,
        *,
        route: str,
        placeholder: str | None = None,
        required: Literal[False],
        pydantic_type: type[str],
        default: str | None = None,
        autocomplete: str | None = None,
        type: str = "search",
        hidden: bool = False,
        read_only: bool = False,
    ) -> None: ...

    def __init__(
        self,
        label: str,
        *,
        route: str,
        placeholder: str | None = None,
        required: bool = True,
        pydantic_type: type = int,
        default = None,
        autocomplete: str | None = None,
        type: str = "search",
        hidden: bool = False,
        read_only: bool = False,
    ):
        super().__init__(
            name=label.lower().replace(" ", "_"),
            label=label,
            template="components/inputs/search-select.html",
            required=required,
            default=default,
            description=None,
            hidden=hidden,
            read_only=read_only,
            type=type,
            pydantic_type=pydantic_type,
        )
        self.route = route
        self.placeholder = placeholder
        self.autocomplete = autocomplete
        self.type = type

    def url(self) -> URL:
        return ctx.request.url_for(self.route)
