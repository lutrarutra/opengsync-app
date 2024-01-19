from typing import Optional, Union
import pandas as pd
from pathlib import Path
from uuid import uuid4

from flask_wtf import FlaskForm
from wtforms import SelectField, FileField
from wtforms.validators import DataRequired, Optional as OptionalValidator

from flask_wtf.file import FileAllowed
from werkzeug.utils import secure_filename

from ... import db, models, logger, tools
from .TableDataForm import TableDataForm


class FeatureInputForm(TableDataForm):
    _required_columns: list[Union[str, list[str]]] = [
        "Sample Name", "Library Name",
    ]
    _allowed_extensions: list[tuple[str, str]] = [
        ("tsv", "Tab-separated"),
        ("csv", "Comma-separated")
    ]

    separator = SelectField(choices=_allowed_extensions, default="tsv")
    file = FileField(validators=[FileAllowed([ext for ext, _ in _allowed_extensions])])

    def prepare(self, df: Optional[pd.DataFrame] = None) -> dict:
        if df is None:
            df = self.get_df()

        self.set_df(df)
        return {}

    def custom_validate(
        self,
    ) -> tuple[bool, "FeatureInputForm"]:

        validated = self.validate()
        if not validated:
            return False, self
        
        if self.file.data is None:
            self.file.errors = ("Upload a file.",)
            return False, self
        
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
            return False, self
        
        missing = []
        for col in FeatureInputForm._required_columns:
            if col not in df.columns:
                missing.append(col)
        
            if len(missing) > 0:
                self.file.errors = (f"Missing column(s): [{', '.join(missing)}]",)
                return False, self
        
        specified_with_name = (~df["Kit"].isna() & ~df["Feature"].isna())
        specified_manually = (~df["Sequence"].isna() & ~df["Pattern"].isna() & ~df["Read"].isna())
        if (~(specified_with_name | specified_manually)).any():
            self.file.errors = ("Columns 'Kit + Feature' or 'Sequence + Pattern Read'  must be specified for all rows.",)
            return False, self
        
        if df["Library Name"].isna().any():
            self.file.errors = ("Column 'Library Name' must be specified for all rows.",)
            return False, self
        
        if df["Sample Name"].isna().any():
            self.file.errors = ("Column 'Sample Name' must be specified for all rows.",)
            return False, self
        
        return validated, self