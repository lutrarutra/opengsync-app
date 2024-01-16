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
        "id", "library_name", "library_type", "index_1", "adapter"
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
        for col in PoolingForm._required_columns:
            if col not in df.columns:
                missing.append(col)
        
            if len(missing) > 0:
                self.file.errors = (f"Missing column(s): [{', '.join(missing)}]",)
                return False, self, df


        if self.index_kit_id.data is not None:
            for i, row in df.iterrows():
                adapter = db.db_handler.get_adapter_from_index_kit(row["adapter"], self.index_kit_id.data)
                
                if adapter.barcode_1 is not None:
                    df.loc[i, "index_1"] = adapter.barcode_1.sequence
                else:
                    df.loc[i, "index_1"] = np.nan
                
                if adapter.barcode_2 is not None:
                    df.loc[i, "index_2"] = adapter.barcode_2.sequence
                else:
                    df.loc[i, "index_2"] = np.nan

                if adapter.barcode_3 is not None:
                    df.loc[i, "index_3"] = adapter.barcode_3.sequence
                else:
                    df.loc[i, "index_3"] = np.nan

                if adapter.barcode_4 is not None:
                    df.loc[i, "index_4"] = adapter.barcode_4.sequence
                else:
                    df.loc[i, "index_4"] = np.nan

        if pd.isna(df["index_1"]).any():
            self.file.errors = ("Missing index_1 value(s) in one or more libraries",)
            return False, self, df

        df.loc[~pd.isna(df["index_1"]), "index_1"] = df.loc[~pd.isna(df["index_1"]), "index_1"].str.strip()
        df.loc[~pd.isna(df["index_2"]), "index_2"] = df.loc[~pd.isna(df["index_2"]), "index_2"].str.strip()
        # df.loc[~pd.isna(df["index_3"]), "index_3"] = df.loc[~pd.isna(df["index_3"]), "index_3"].str.strip()
        # df.loc[~pd.isna(df["index_4"]), "index_4"] = df.loc[~pd.isna(df["index_4"]), "index_4"].str.strip()
            
        return validated, self, df