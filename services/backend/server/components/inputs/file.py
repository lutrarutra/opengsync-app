from typing import Any, Generic, Literal, TypeVar, overload
from pydantic import BaseModel

from .BaseInputField import BaseInputField

class FileUpload(BaseModel):    
    filename: str
    content: bytes
    content_type: str
    size: int

_DataT = TypeVar("_DataT", FileUpload, FileUpload | None, covariant=True)


class FileInputField(BaseInputField, Generic[_DataT]):
    """File upload input field.

    Renders an HTML file input with optional file type restrictions.
    File validation (size, extension) is handled at the form level.

    During validation the middleware stores file data as a dict with keys
    ``filename``, ``content`` (bytes), ``content_type``, and ``size``.  Use the
    properties below to access them instead of indexing ``.data`` directly.

    When ``required=True`` the type variable is ``dict`` and ``.data`` is
    typed as ``dict``; when ``required=False`` it is ``dict | None``.
    """

    @overload
    def __init__(
        self: "FileInputField[FileUpload]",
        label: str,
        *,
        max_size: int | None = None,
        allowed_extensions: list[str] | None = None,
        description: str | None = None,
        required: Literal[True] = True,
        hidden: bool = False,
        read_only: bool = False,
    ) -> None: ...

    @overload
    def __init__(
        self: "FileInputField[FileUpload | None]",
        label: str,
        *,
        max_size: int | None = None,
        allowed_extensions: list[str] | None = None,
        description: str | None = None,
        required: Literal[False],
        hidden: bool = False,
        read_only: bool = False,
    ) -> None: ...

    def __init__(
        self,
        label: str,
        *,
        max_size: int | None = None,
        allowed_extensions: list[str] | None = None,
        description: str | None = None,
        default: Any = None,
        required: bool = True,
        hidden: bool = False,
        read_only: bool = False,
    ):
        super().__init__(
            label=label,
            template="components/inputs/file.html",
            type="file",
            default=default,
            pydantic_type=Any,
            description=description,
            required=required,
            hidden=hidden,
            read_only=read_only,
        )
        self.max_size = max_size
        self.allowed_extensions = allowed_extensions or []
        self.accept = (
            ",".join(f".{ext.lstrip('.')}" for ext in self.allowed_extensions)
            if self.allowed_extensions
            else ""
        )

    @property
    def data(self) -> _DataT:
        if self._validated:
            if self._data is None:
                return None  # type: ignore
            return FileUpload.model_validate(self._data, from_attributes=True)  # type: ignore
        return None  # type: ignore

    # @property
    # def filename(self) -> str | None:
    #     """The original filename uploaded by the user."""
    #     d = self.data
    #     return d["filename"] if isinstance(d, dict) else None

    # @property
    # def content(self) -> bytes | None:
    #     """Raw file content as bytes."""
    #     d = self.data
    #     return d["content"] if isinstance(d, dict) else None

    # @property
    # def content_type(self) -> str | None:
    #     """MIME type reported by the client (e.g. ``image/png``)."""
    #     d = self.data
    #     return d.get("content_type") if isinstance(d, dict) else None

    # @property
    # def size(self) -> int | None:
    #     """Size of the uploaded file in bytes."""
    #     d = self.data
    #     return d.get("size") if isinstance(d, dict) else None