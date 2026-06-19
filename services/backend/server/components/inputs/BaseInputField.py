from typing import Any
from abc import ABC
from markupsafe import Markup

from ...core.templates import render_template


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
        self.data = default
        self.errors: list[str] = []
        self.pydantic_type = pydantic_type
        self.required = required
        self.hidden = hidden
        self.description = description
        self.read_only = read_only

    async def render(self, container_class="", hide_label: bool = False) -> str:
        return Markup(
            await render_template(
                self.template,
                field=self,
                container_class=container_class,
                hide_label=hide_label,
            )
        )
