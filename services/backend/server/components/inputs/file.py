from typing import Any
from .BaseInputField import BaseInputField


class FileInputField(BaseInputField):
    """File upload input field.

    Renders an HTML file input with optional file type restrictions.
    File validation (size, extension) is handled at the form level.

    During validation the middleware stores file data as a dict with keys
    ``filename``, ``content`` (bytes), and ``content_type``.  Use the
    properties below to access them instead of indexing ``.data`` directly.
    """

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
            pydantic_type=dict,
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
    def filename(self) -> str | None:
        """The original filename uploaded by the user."""
        d = self.data
        return d["filename"] if isinstance(d, dict) else None

    @property
    def content(self) -> bytes | None:
        """Raw file content as bytes."""
        d = self.data
        return d["content"] if isinstance(d, dict) else None

    @property
    def content_type(self) -> str | None:
        """MIME type reported by the client (e.g. ``image/png``)."""
        d = self.data
        return d.get("content_type") if isinstance(d, dict) else None