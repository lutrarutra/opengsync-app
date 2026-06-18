from typing import Any, Annotated, Generic, Literal, TypeVar, overload
from pydantic import AfterValidator
from .InputField import InputField

_FloatDataT = TypeVar("_FloatDataT", float, float | None, covariant=True)


class FloatInputField(InputField, Generic[_FloatDataT]):
    data: _FloatDataT

    @overload
    def __init__(
        self: "FloatInputField[float]",
        label: str,
        *,
        required: Literal[True] = True,
        placeholder: str | None = None,
        ge: float | None = None,
        le: float | None = None,
        description: str | None = None,
        default: float | None = None,
        hidden: bool = False,
        read_only: bool = False,
    ) -> None: ...

    @overload
    def __init__(
        self: "FloatInputField[float | None]",
        label: str,
        *,
        required: Literal[False],
        placeholder: str | None = None,
        ge: float | None = None,
        le: float | None = None,
        description: str | None = None,
        default: float | None = None,
        hidden: bool = False,
        read_only: bool = False,
    ) -> None: ...

    def __init__(
        self, label: str,
        placeholder: str | None = None,
        ge: float | None = None,
        le: float | None = None,
        description: str | None = None,
        default: float | None = None,
        required: bool = True,
        hidden: bool = False,
        read_only: bool = False,
    ):
        pydantic_type: Any = float

        if ge is not None or le is not None:
            constraints = []
            if ge is not None:
                constraints.append(f"must be >= {ge}")
            if le is not None:
                constraints.append(f"must be <= {le}")

            def _validate(x: float) -> float:
                if ge is not None and x < ge:
                    raise ValueError(f"Value must be >= {ge}")
                if le is not None and x > le:
                    raise ValueError(f"Value must be <= {le}")
                return x

            pydantic_type = Annotated[float, AfterValidator(_validate)]

        super().__init__(
            name=label.lower().replace(" ", "_"),
            label=label,
            template="components/inputs/numeric.html",
            type="number",
            default=default,
            pydantic_type=pydantic_type,
            description=description,
            required=required,
            hidden=hidden,
            read_only=read_only,
        )
        self.placeholder = placeholder
        self.ge = ge
        self.le = le


_IntDataT = TypeVar("_IntDataT", int, int | None, covariant=True)


class IntInputField(InputField, Generic[_IntDataT]):
    data: _IntDataT

    @overload
    def __init__(
        self: "IntInputField[int]",
        label: str,
        *,
        required: Literal[True] = True,
        placeholder: str | None = None,
        ge: int | None = None,
        le: int | None = None,
        description: str | None = None,
        default: int | None = None,
        hidden: bool = False,
        read_only: bool = False,
    ) -> None: ...

    @overload
    def __init__(
        self: "IntInputField[int | None]",
        label: str,
        *,
        required: Literal[False],
        placeholder: str | None = None,
        ge: int | None = None,
        le: int | None = None,
        description: str | None = None,
        default: int | None = None,
        hidden: bool = False,
        read_only: bool = False,
    ) -> None: ...

    def __init__(
        self, label: str,
        placeholder: str | None = None,
        ge: int | None = None,
        le: int | None = None,
        description: str | None = None,
        default: int | None = None,
        required: bool = True,
        hidden: bool = False,
        read_only: bool = False,
    ):
        pydantic_type: Any = int

        if ge is not None or le is not None:
            def _validate(x: int) -> int:
                if ge is not None and x < ge:
                    raise ValueError(f"Value must be >= {ge}")
                if le is not None and x > le:
                    raise ValueError(f"Value must be <= {le}")
                return x

            pydantic_type = Annotated[int, AfterValidator(_validate)]

        super().__init__(
            name=label.lower().replace(" ", "_"),
            label=label,
            template="components/inputs/numeric.html",
            type="number",
            default=default,
            pydantic_type=pydantic_type,
            description=description,
            required=required,
            hidden=hidden,
            read_only=read_only,
        )
        self.placeholder = placeholder
        self.ge = ge
        self.le = le