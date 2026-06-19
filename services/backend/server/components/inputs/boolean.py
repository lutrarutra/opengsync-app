from typing import Any
from .BaseInputField import BaseInputField


class BooleanInputField(BaseInputField):
    """Boolean checkbox/switch input field.

    Always required - it's either checked (on) or unchecked (off).
    The form data sends 'on' when checked, or nothing when unchecked.
    """

    def __init__(
        self,
        label: str,
        *,
        default: bool = False,
        description: str | None = None,
        template: str | None = None,
        hidden: bool = False,
        read_only: bool = False,
    ):
        super().__init__(
            label=label,
            template=template or "components/inputs/boolean.html",
            default=default,
            pydantic_type=bool,
            type="checkbox",
            description=description,
            required=True,
            hidden=hidden,
            read_only=read_only,
        )

    def validate_value(self, raw_value: Any) -> bool:
        """Convert raw form value to boolean.

        Checkboxes send 'on' when checked, or nothing when unchecked.
        """
        if raw_value is None:
            return False
        if isinstance(raw_value, bool):
            return raw_value
        if isinstance(raw_value, str):
            return raw_value.lower() in ("on", "true", "1", "yes")
        return bool(raw_value)


class CheckboxInputField(BooleanInputField):
    """Boolean checkbox input field."""

    def __init__(
        self,
        label: str,
        *,
        default: bool = False,
        description: str | None = None,
        hidden: bool = False,
        read_only: bool = False,
    ):
        super().__init__(
            label=label,
            default=default,
            description=description,
            template="components/inputs/checkbox.html",
            hidden=hidden,
            read_only=read_only,
        )


class SwitchInputField(BooleanInputField):
    """Boolean switch input field."""

    def __init__(
        self,
        label: str,
        *,
        default: bool = False,
        description: str | None = None,
        hidden: bool = False,
        read_only: bool = False,
    ):
        super().__init__(
            label=label,
            default=default,
            description=description,
            template="components/inputs/switch.html",
            hidden=hidden,
            read_only=read_only,
        )
