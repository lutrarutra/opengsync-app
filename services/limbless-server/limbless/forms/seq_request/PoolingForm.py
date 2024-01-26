from typing import Literal, Optional
from uuid import uuid4
from pathlib import Path

import pandas as pd
import numpy as np

from wtforms import IntegerField, SelectField
from wtforms.validators import Optional as OptionalValidator
from flask_wtf.file import FileField, FileAllowed
from werkzeug.utils import secure_filename

from ... import db, logger
from .TableDataForm import TableDataForm


class PoolingForm(TableDataForm):
    _required_columns: list[str] = [
        "id", "library_name", "library_type", "index_1", "adapter", "pool", "index_kit"
    ]
    _allowed_extensions: list[tuple[str, str]] = [
        ("tsv", "Tab-separated"),
        ("csv", "Comma-separated")
    ]

    separator = SelectField(choices=_allowed_extensions, default="tsv")
    file = FileField(validators=[FileAllowed([ext for ext, _ in _allowed_extensions])])

    def custom_validate(
        self,
    ) -> tuple[bool, "PoolingForm", Optional[pd.DataFrame]]:

        validated = self.validate()
        if not validated:
            return False, self, None
        
        if self.file.data is None:
            self.file.errors = ("Upload a file.",)
            return False, self, None
        
        filename = f"{Path(self.file.data.filename).stem}_{uuid4()}.{self.file.data.filename.split('.')[-1]}"
        filename = secure_filename(filename)
        self.file.data.save("uploads/" + filename)
        logger.debug(f"Saved file to data/uploads/{filename}")

        if self.separator.data == "tsv":
            sep = "\t"
        else:
            sep = ","
        
        try:
            df = pd.read_csv("uploads/" + filename, sep=sep, index_col=False, header=0)
        except pd.errors.ParserError as e:
            self.file.errors = (str(e),)
            return False, self, None

        missing = []
        logger.debug(df.columns)
        for col in PoolingForm._required_columns:
            if col not in df.columns:
                missing.append(col)
        
            if len(missing) > 0:
                self.file.errors = (f"Missing column(s): [{', '.join(missing)}]",)
                return False, self, df

        return validated, self, df