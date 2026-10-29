from typing import Any

from starlette.datastructures import URL

from opengsync_db import SyncSession

from .BaseInputField import BaseInputField
from ...core import column_values
from ...core.context import ctx


class ColumnValueInputField(BaseInputField):
    """Select a value of a free-text column, or type a new one (core/column_values.py).

    Options are identified by the normalized key of their value: the field submits ``<name>`` (the key, ``new``
    or empty) and ``<name>-text`` (the value as shown). ``data`` is the key or, for a new value, the typed name;
    ``resolve`` turns it into the values to store, snapping new values to an existing spelling.

    ``query_fields`` maps query parameters of the search to ids of other fields whose shown value filters the
    options (e.g. departments of the selected institute); ``query_params`` are fixed parameters (e.g. the token of a
    page whose user is not logged in). Uses the search-select widget (static/js/search-select.js).
    """

    NEW = "new"

    def __init__(
        self,
        label: str,
        *,
        source: str,
        placeholder: str | None = None,
        required: bool = True,
        allow_new: bool = True,
        new_label: str = "Create New",
        new_min_length: int | None = None,
        new_max_length: int | None = None,
        description: str | None = None,
        hidden: bool = False,
        read_only: bool = False,
    ):
        if source not in column_values.SOURCES:
            raise ValueError(f"Unknown column value source '{source}'.")
        super().__init__(
            label=label,
            template="components/inputs/column-value.html",
            required=required,
            description=description,
            hidden=hidden,
            read_only=read_only,
            type="search",
        )
        self.source = source
        self.placeholder = placeholder
        self.allow_new = allow_new
        self.new_label = new_label
        self.new_min_length = new_min_length
        self.new_max_length = new_max_length
        self.query_params: dict[str, str] = {}
        self.query_fields: dict[str, str] = {}
        self.text: str | None = None
        self._is_new = False

    @property
    def column_source(self) -> column_values.ColumnSource:
        return column_values.SOURCES[self.source]

    def url(self) -> URL:
        return ctx.request.url_for("search_column_values", source=self.source).include_query_params(**self.query_params)

    @property
    def text_name(self) -> str:
        return f"{self.name}-text"

    @property
    def is_new(self) -> bool:
        return self._is_new and bool(self.data)

    @property
    def value(self) -> str:
        """The submitted value: the key, ``new`` or empty."""
        if not self.data:
            return ""
        return self.NEW if self.is_new else str(self.data)

    @property
    def display_text(self) -> str:
        if self.is_new:
            return str(self.data)
        return (self.text or "") if self.value else ""

    def _set(self, value: str | None, *, is_new: bool, text: str | None) -> None:
        self._data = value
        self._validated = True
        self._is_new = is_new
        self.text = text

    def set_values(self, values: tuple[str | None, ...] | None) -> None:
        """Prefill with stored values (the first is shown); empty if any is missing."""
        if not values or not all(values):
            self._set(None, is_new=False, text=None)
            return
        self._set(column_values.key_of(self.column_source, values), is_new=False, text=values[0])  # type: ignore[arg-type]

    def clear(self) -> None:
        self._set(None, is_new=False, text=None)

    def validate(self, raw_data: dict[str, Any]) -> bool:
        self._self_validated = True
        text = raw_data.get(self.text_name)
        text = " ".join(text.split()) if isinstance(text, str) else ""
        value = raw_data.get(self.name)
        value = value.strip() if isinstance(value, str) else ""

        if not value:
            self._set(None, is_new=False, text=None)
            if self.required and not self.errors:  # the form may have reported it already
                self.errors.append(f"{self.label} is required.")
            return not self.errors

        if value == self.NEW:
            self._set(text or None, is_new=True, text=text or None)
            if not self.allow_new:
                self.errors.append(f"Select an existing {self.label.lower()}.")
            elif not text:
                self.errors.append(f"Enter a name for the new {self.label.lower()}.")
            elif self.new_min_length is not None and len(text) < self.new_min_length:
                self.errors.append(f"{self.label} should have at least {self.new_min_length} characters.")
            elif self.new_max_length is not None and len(text) > self.new_max_length:
                self.errors.append(f"{self.label} should have at most {self.new_max_length} characters.")
            return not self.errors

        self._set(value, is_new=False, text=text or None)
        return not self.errors

    def resolve(
        self,
        session: SyncSession,
        *,
        filters: dict[str, str | None] | None = None,
        new_extra: tuple[str, ...] = (),
    ) -> tuple[str, ...] | None:
        """The values to store: those of the selected key, or the new name (plus ``new_extra``, e.g. a new PI's
        email) snapped to an existing spelling. None if empty; records an error for an unknown key or one not matching
        ``filters`` (e.g. a department of another institute)."""
        if not self.data:
            return None
        if self.is_new:
            values = column_values.resolve_new(session, self.column_source, (str(self.data), *new_extra), filters)
        else:
            found = column_values.lookup(session, self.column_source, str(self.data), filters)
            if found is None:
                active = {name: value for name, value in (filters or {}).items() if value}
                if active and (other := column_values.lookup(session, self.column_source, str(self.data))):
                    self.errors.append(
                        f"{other[0]} is not a {self.label.lower()} of {', '.join(active.values())}: "
                        "select another one or create it as new."
                    )
                else:
                    self.errors.append(f"Invalid {self.label.lower()} selected.")
                return None
            values = found
        self.text = values[0]
        return values
