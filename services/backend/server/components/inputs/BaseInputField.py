from typing import Any
from abc import ABC
from markupsafe import Markup

from ...core.templates import render_template
from ...core.context import get_request_context


class BaseInputField(ABC):
    def __init__(
        self,
        label: str,
        template: str,
        type: str,
        id: str | None = None,
        default: Any = None,
        required: bool = True,
        pydantic_type: Any = str,
        hidden: bool = False,
        description: str | None = None,
        read_only: bool = False,
    ):
        self.label = label
        self.template = template
        self.type = type
        self.id = id or ""
        self.name = self.id
        self.default = default
        self._data: Any = None
        self._validated: bool = False
        self.raw_data: Any = None
        self.errors: list[str] = []
        self.pydantic_type = pydantic_type
        self.required = required
        self.hidden = hidden
        self.description = description
        self.read_only = read_only
        self._self_validated: bool = False

    @property
    def data(self) -> Any:
        """Validated/processed data for this field.

        Returns the validated value if the form has been validated, otherwise
        falls back to ``default`` (used during rendering before validation).
        """
        if self._validated:
            return self._data
        return self.default

    @data.setter
    def data(self, value: Any) -> None:
        self._data = value
        self._validated = True

    def validate(self, raw_data: dict[str, Any]) -> bool:
        """Validate this field against the submitted form data.

        Default implementation does nothing — Pydantic validation is handled
        at the form level. Override in subclasses that need custom validation
        (e.g. ``SpreadsheetInputField``). If overridden, set
        ``self._self_validated = True`` so the form skips Pydantic for this
        field.

        Args:
            raw_data: The full form data dictionary.

        Returns:
            True if validation succeeded, False otherwise.
            Errors should be recorded in ``self.errors``.
        """
        return True

    def render(self, container_class: str = "", hide_label: bool = False, hide_errors: bool = False, **kwargs) -> str:
        return Markup(
            render_template(
                self.template,
                field=self,
                container_class=container_class,
                hide_label=hide_label,
                hide_errors=hide_errors,
                **kwargs,
                **get_request_context(),
            )
        )
