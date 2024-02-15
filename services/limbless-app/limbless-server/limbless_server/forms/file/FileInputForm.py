from typing import Optional

from flask_wtf.file import FileField, FileAllowed
from wtforms.validators import DataRequired, Optional as OptionalValidator, Length
from wtforms import SelectField, TextAreaField
from flask import Response

from limbless_db import models
from limbless_db.core.categories import FileType
from ..HTMXFlaskForm import HTMXFlaskForm


class FileInputForm(HTMXFlaskForm):
    _template_path = "components/popups/file-input-form.html"
    _form_label = "file_input_form"
    _allowed_extensions: list[tuple[str, str]] = [
        ("tsv", "Tab-separated"),
        ("csv", "Comma-separated"),
        ("pdf", "PDF"),
        ("png", "PNG"),
        ("jpg", "JPEG"),
        ("jpeg", "JPEG")
    ]
    file_type = SelectField("File Type", choices=FileType.as_selectable(), coerce=int, description="Select the type of file you are uploading.")
    comment = TextAreaField("Comment", validators=[OptionalValidator(), Length(max=models.Comment.text.type.length)], description="Provide a brief description of the file.")
    file = FileField(validators=[DataRequired(), FileAllowed([ext for ext, _ in _allowed_extensions])])

    def __init__(self, formdata: Optional[dict] = None, max_size_mbytes: int = 5):
        super().__init__(formdata=formdata)
        self.max_size_mbytes = max_size_mbytes

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        max_bytes = self.max_size_mbytes * 1024 * 1024
        size_bytes = len(self.file.data.read())
        self.file.data.seek(0)

        if size_bytes > max_bytes:
            self.file.errors = (f"File size exceeds {self.max_size_mbytes} MB",)
            return False
        
        return True
    
    def process_request(self, **context) -> Response:
        raise NotImplementedError("Subclasses must implement this method.")
        
