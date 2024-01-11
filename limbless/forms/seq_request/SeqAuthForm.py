    
from flask_wtf import FlaskForm
from wtforms import FileField
from wtforms.validators import DataRequired
from flask_wtf.file import FileAllowed


class SeqAuthForm(FlaskForm):
    file = FileField(
        "Sequencing Authorization Form",
        validators=[DataRequired(), FileAllowed(["pdf"])],
    )

    def custom_validate(self) -> tuple[bool, "SeqAuthForm"]:
        validated = self.validate()

        if not validated:
            return False, self

        # Max size 3
        MAX_MBYTES = 3
        max_bytes = MAX_MBYTES * 1024 * 1024

        if len(self.file.data.read()) > max_bytes:
            validated = False
            self.file.errors = (f"File size exceeds {MAX_MBYTES} MB",)
        self.file.data.seek(0)
        
        return True, self