from typing import Generic, Literal, TypeVar, overload
from starlette.datastructures import URL

from .BaseInputField import BaseInputField
from ...core.context import ctx

_SearchableDataT = TypeVar("_SearchableDataT", int, int | None, covariant=True)


class SearchableInputField(BaseInputField, Generic[_SearchableDataT]):
    data: _SearchableDataT

    @overload
    def __init__(
        self: "SearchableInputField[int]",
        label: str,
        *,
        route: str,
        placeholder: str | None = None,
        required: Literal[True] = True,
        pydantic_type: type = int,
        default=None,
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
        pydantic_type: type = int,
        default=None,
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
        default=None,
        autocomplete: str | None = None,
        type: str = "search",
        hidden: bool = False,
        read_only: bool = False,
    ):
        super().__init__(
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
