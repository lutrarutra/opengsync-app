from typing import Any, Generic, Literal, TypeVar, overload
from starlette.datastructures import URL

from .BaseInputField import BaseInputField
from ...core.context import ctx

_SearchableDataT = TypeVar("_SearchableDataT", int, int | None, int | str, int | str | None, covariant=True)


class SearchableInputField(BaseInputField, Generic[_SearchableDataT]):
    """Select an object searched on the backend, optionally typing a new one instead.

    ``route`` names a search route that takes ``word``, ``page`` and ``selected_id`` (plus ``query_params``) and
    returns ``responses.query_options_response``: ``{"options": [{"id", "name", "header"?, "description"?}],
    "has_more"}`` (static/js/search-select.js).

    The field submits two inputs: ``<name>`` holds the id of the selected option, and ``<name>-text`` its name as
    shown, so a re-rendered form shows it without looking it up again. Ids without a name are looked up with
    ``selected_id``; callers that know the name may set ``text``.

    With ``allow_new`` the user may instead create a new option from the typed text: ``<name>`` is then ``new``
    and ``<name>-text`` the new name, and ``data`` is that name (stripped and checked against ``new_min_length``
    and ``new_max_length``) instead of an id. Creating the object, and checking it is not a duplicate, is up to
    the form. Elements with ``data-search-select-new-only="<field id>"`` are shown (and their inputs submitted) only
    while the field holds a new name.
    """

    NEW = "new"

    data: _SearchableDataT

    @overload
    def __init__(
        self: "SearchableInputField[int]",
        label: str,
        *,
        route: str,
        placeholder: str | None = None,
        required: Literal[True] = True,
        allow_new: Literal[False] = False,
        new_label: str = "Create New",
        new_min_length: int | None = None,
        new_max_length: int | None = None,
        pydantic_type: type = int,
        default=None,
        autocomplete: str | None = None,
        type: str = "search",
        hidden: bool = False,
        read_only: bool = False,
        query_params: dict | None = None,
    ) -> None: ...

    @overload
    def __init__(
        self: "SearchableInputField[int | None]",
        label: str,
        *,
        route: str,
        placeholder: str | None = None,
        required: Literal[False],
        allow_new: Literal[False] = False,
        new_label: str = "Create New",
        new_min_length: int | None = None,
        new_max_length: int | None = None,
        pydantic_type: type = int,
        default=None,
        autocomplete: str | None = None,
        type: str = "search",
        hidden: bool = False,
        read_only: bool = False,
        query_params: dict | None = None,
    ) -> None: ...

    @overload
    def __init__(
        self: "SearchableInputField[int | str]",
        label: str,
        *,
        route: str,
        placeholder: str | None = None,
        required: Literal[True] = True,
        allow_new: Literal[True],
        new_label: str = "Create New",
        new_min_length: int | None = None,
        new_max_length: int | None = None,
        pydantic_type: type = int,
        default=None,
        autocomplete: str | None = None,
        type: str = "search",
        hidden: bool = False,
        read_only: bool = False,
        query_params: dict | None = None,
    ) -> None: ...

    @overload
    def __init__(
        self: "SearchableInputField[int | str | None]",
        label: str,
        *,
        route: str,
        placeholder: str | None = None,
        required: Literal[False],
        allow_new: Literal[True],
        new_label: str = "Create New",
        new_min_length: int | None = None,
        new_max_length: int | None = None,
        pydantic_type: type = int,
        default=None,
        autocomplete: str | None = None,
        type: str = "search",
        hidden: bool = False,
        read_only: bool = False,
        query_params: dict | None = None,
    ) -> None: ...

    def __init__(
        self,
        label: str,
        *,
        route: str,
        placeholder: str | None = None,
        required: bool = True,
        allow_new: bool = False,
        new_label: str = "Create New",
        new_min_length: int | None = None,
        new_max_length: int | None = None,
        pydantic_type: type = int,
        default=None,
        autocomplete: str | None = None,
        type: str = "search",
        hidden: bool = False,
        read_only: bool = False,
        query_params: dict | None = None,
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
        self.query_params = query_params or {}
        self.allow_new = allow_new
        self.new_label = new_label
        self.new_min_length = new_min_length
        self.new_max_length = new_max_length
        self.text: str | None = None
        self._new_name: str | None = None

    def url(self) -> URL:
        return ctx.request.url_for(self.route).include_query_params(**self.query_params)

    @property
    def text_name(self) -> str:
        return f"{self.name}-text"

    def set_selected(self, id: int | None, text: str | None = None) -> None:
        """Prefill the selection, with its name if known (otherwise the page looks it up)."""
        self._set(id)
        self.text = text

    def set_new(self, name: str) -> None:
        """Prefill a new name (``allow_new`` only)."""
        self._set(name)
        self.text = name

    @property
    def is_new(self) -> bool:
        """The field holds a new name instead of an id."""
        if not self.allow_new or not isinstance(self.data, str):
            return False
        # Re-rendered sub-forms hold the submitted value (an id or "new") instead of the validated one
        return self.data == self.NEW or self.data == self._new_name or not self.data.isdigit()

    @property
    def value(self) -> str:
        """The submitted value: the id, ``new`` or empty. Unvalidated data (e.g. after errors) may be a string."""
        if self.is_new:
            return self.NEW
        data = self.data
        if isinstance(data, bool):
            return ""
        if isinstance(data, int) or (isinstance(data, str) and data.isdigit()):
            return str(data)
        return ""

    @property
    def display_text(self) -> str:
        """The name shown in the input: the new name, or the name of the selected option if known."""
        if self.is_new:
            return self.text or "" if self.data == self.NEW else str(self.data)
        return (self.text or "") if self.value else ""

    def _set(self, value: int | str | None) -> None:
        self._data = value
        self._validated = True
        self._new_name = value if isinstance(value, str) else None

    def validate(self, raw_data: dict[str, Any]) -> bool:
        text = raw_data.get(self.text_name)
        self.text = text.strip() or None if isinstance(text, str) else None

        # Ids are validated by the form (pydantic) unless the field may hold a new name
        if not self.allow_new:
            return True
        self._self_validated = True

        value = raw_data.get(self.name)
        value = value.strip() if isinstance(value, str) else value
        if value is None or value == "":
            # A missing required value is already reported by the form
            self._set(None)
            return not self.errors

        if value == self.NEW:
            name = self.text or ""
            self._set(name)
            if not name:
                self.errors.append(f"Enter a name for the new {self.label.lower()}.")
            elif self.new_min_length is not None and len(name) < self.new_min_length:
                self.errors.append(f"{self.label} should have at least {self.new_min_length} characters.")
            elif self.new_max_length is not None and len(name) > self.new_max_length:
                self.errors.append(f"{self.label} should have at most {self.new_max_length} characters.")
            return not self.errors

        try:
            self._set(int(value))
        except (TypeError, ValueError):
            self._set(None)
            self.errors.append(f"Invalid {self.label.lower()} selected.")
            return False
        return not self.errors
