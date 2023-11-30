from typing import Optional
from io import StringIO
from uuid import uuid4

import pandas as pd

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, DataRequired
from wtforms import TextAreaField, SelectField
from werkzeug.utils import secure_filename

from .. import logger


class TableForm(FlaskForm):
    _allowed_extensions: list[tuple[str, str]] = [
        ("tsv", "Tab-separated"),
        ("csv", "Comma-separated")
    ]
    separator = SelectField(choices=_allowed_extensions, default="tsv")
    file = FileField(validators=[FileAllowed([ext for ext, _ in _allowed_extensions])])
    raw_data = TextAreaField("Data")

    def custom_validate(self):
        validated = self.validate()
        if not validated:
            return False, self
        
        file_field_empty = self.file.data is None
        data_field_empty = self.raw_data.data == "" or self.raw_data.data is None

        if file_field_empty and data_field_empty:
            self.file.errors = ("Please upload a file or paste data.",)
            self.raw_data.errors = ("Please upload a file or paste data.",)
            validated = False

        elif (not file_field_empty) and (not data_field_empty):
            self.file.errors = ("Please upload a file or paste data, not both.",)
            self.raw_data.errors = ("Please upload a file or paste data, not both.",)
            validated = False

        return validated, self
    
    def parse(self) -> pd.DataFrame:
        if self.separator.data == "tsv":
            sep = "\t"
        else:
            sep = ","

        if self.raw_data.data:
            raw_text = self.raw_data.data
        else:
            filename = f"{self.file.data.filename.split('.')[0]}_{uuid4()}.{self.file.data.filename.split('.')[-1]}"
            filename = secure_filename(filename)
            self.file.data.save("data/uploads/" + filename)
            logger.debug(f"Saved file to data/uploads/{filename}")
            raw_text = open("data/uploads/" + filename).read()

        df = pd.read_csv(StringIO(raw_text.rstrip()), sep=sep, index_col=False, header=0)
        
        return df

        
