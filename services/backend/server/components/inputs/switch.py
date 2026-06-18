from .InputField import InputField


class SwitchInputField(InputField):
    data: bool

    def __init__(
        self,
        label: str,
        *,
        default: bool = False,
        description: str | None = None,
    ):
        super().__init__(
            name=label.lower().replace(" ", "_"),
            label=label,
            template="components/inputs/switch.html",
            default=default,
            pydantic_type=bool,
            type="switch",
            description=description,
            required=False,
        )
