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

    def prepare(self, data: Optional[dict[str, pd.DataFrame]] = None) -> dict:
        if data is None:
            data = self.data

        # self.update_data(data)
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
        self.file.data.save("uploads/seq_request/" + filename)
        logger.debug(f"Saved file to uploads/seq_request/{filename}")

        if self.separator.data == "tsv":
            sep = "\t"
        else:
            sep = ","

        try:
            self.feature_ref = pd.read_csv("uploads/seq_request/" + filename, sep=sep, index_col=False, header=0)
        except pd.errors.ParserError as e:
            self.file.errors = (str(e),)
            return False, self
        
        missing = []
        for col in FeatureInputForm._required_columns:
            if col not in self.feature_ref.columns:
                missing.append(col)
        
            if len(missing) > 0:
                self.file.errors = (f"Missing column(s): [{', '.join(missing)}]",)
                return False, self
        
        specified_with_name = (~self.feature_ref["Kit"].isna() & ~self.feature_ref["Feature"].isna())
        specified_manually = (~self.feature_ref["Sequence"].isna() & ~self.feature_ref["Pattern"].isna() & ~self.feature_ref["Read"].isna())
        if (~(specified_with_name | specified_manually)).any():
            self.file.errors = ("Columns 'Kit + Feature' or 'Sequence + Pattern Read'  must be specified for all rows.",)
            return False, self
        
        if self.feature_ref["Library Name"].isna().any():
            self.file.errors = ("Column 'Library Name' must be specified for all rows.",)
            return False, self
        
        if self.feature_ref["Sample Name"].isna().any():
            self.file.errors = ("Column 'Sample Name' must be specified for all rows.",)
            return False, self
        
        data = self.data

        libraries_not_mapped = ~self.feature_ref["Library Name"].isin(data["sample_table"]["sample_name"])
        if libraries_not_mapped.any():
            self.file.errors = (
                "Values in 'Library Name'-column in feature reference must be found in 'Sample/Library Name'-column of sample annotation sheet.",
                "Missing values: " + ", ".join(self.feature_ref["Library Name"][libraries_not_mapped].unique().tolist())
            )
            return False, self
        
        return validated, self
    
    def parse(self) -> dict[str, pd.DataFrame]:
        data = self.data

        self.feature_ref = self.feature_ref.rename(columns={
            "Sample Name": "sample_name",
            "Library Name": "library_name",
            "Kit": "feature_kit",
            "Feature": "feature_name",
            "Sequence": "sequence",
            "Pattern": "pattern",
            "Read": "read",
        })

        data["feature_table"] = self.feature_ref

        self.update_data(data)

        return data