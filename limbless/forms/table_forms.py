from typing import Optional
from uuid import uuid4
from pathlib import Path

import pandas as pd

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, DataRequired
from wtforms import SelectField
from werkzeug.utils import secure_filename

from .. import logger


class TableForm(FlaskForm):
    _allowed_extensions: list[tuple[str, str]] = [
        ("tsv", "Tab-separated"),
        ("csv", "Comma-separated")
    ]
    separator = SelectField(choices=_allowed_extensions, default="tsv")
    file = FileField(validators=[FileAllowed([ext for ext, _ in _allowed_extensions])])

    def custom_validate(self) -> tuple[bool, "TableForm"]:
        validated = self.validate()
        if not validated:
            return False, self

        if self.file.data is None:
            self.file.errors = ("Please upload a file.",)
            validated = False

        return validated, self
    
    def parse(self) -> pd.DataFrame:
        if self.separator.data == "tsv":
            sep = "\t"
        else:
            sep = ","

        filename = f"{Path(self.file.data.filename).stem}_{uuid4()}.{self.file.data.filename.split('.')[-1]}"
        filename = secure_filename(filename)
        self.file.data.save("data/uploads/" + filename)
        logger.debug(f"Saved file to data/uploads/{filename}")

        df = pd.read_csv("data/uploads/" + filename, sep=sep, index_col=False, header=0)
        
        return df

        
