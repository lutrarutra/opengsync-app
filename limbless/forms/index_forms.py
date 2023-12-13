from typing import Literal, Optional
from uuid import uuid4
from pathlib import Path

import pandas as pd

from flask_wtf import FlaskForm
from wtforms import IntegerField, SelectField
from wtforms.validators import Optional as OptionalValidator
from flask_wtf.file import FileField, FileAllowed
from werkzeug.utils import secure_filename

from ..models import Library
from ..core.DBHandler import DBHandler
from ..core.DBSession import DBSession
from .. import logger


class IndexForm(FlaskForm):
    _required_columns: list[str] = [
        "library_id", "library_name", "library_type", "index_1", "adapter"
    ]
    _allowed_extensions: list[tuple[str, str]] = [
        ("tsv", "Tab-separated"),
        ("csv", "Comma-separated")
    ]
    index_kit_id = IntegerField(
        "Index Kit", validators=[OptionalValidator()]
    )
    separator = SelectField(choices=_allowed_extensions, default="tsv")
    file = FileField(validators=[FileAllowed([ext for ext, _ in _allowed_extensions])])

    def custom_validate(
        self,
    ) -> tuple[bool, "IndexForm", Optional[pd.DataFrame]]:

        validated = self.validate()
        if not validated:
            return False, self, None
        
        if self.file.data is None:
            self.file.errors = ("Upload a file.",)
            return False, self, None
        
        filename = f"{Path(self.file.data.filename).stem}_{uuid4()}.{self.file.data.filename.split('.')[-1]}"
        filename = secure_filename(filename)
        self.file.data.save("data/uploads/" + filename)
        logger.debug(f"Saved file to data/uploads/{filename}")

        if self.separator.data == "tsv":
            sep = "\t"
        else:
            sep = ","
        
        try:
            df = pd.read_csv("data/uploads/" + filename, sep=sep, index_col=False, header=0)
        except pd.errors.ParserError as e:
            self.file.errors = (str(e),)
            return False, self, None

        missing = []
        for col in IndexForm._required_columns:
            if col not in df.columns:
                missing.append(col)
        
            if len(missing) > 0:
                self.file.errors = (f"Missing column(s): [{', '.join(missing)}]",)
                return False, self, df
            
            if pd.isna(df["index_1"]).any():
                self.file.errors = ("Missing index_1 value(s) in one or more libraries",)
                return False, self, df
            
        adapter_set, adapter_1_set, adapter_2_set, adapter_3_set, adapter_4_set = self.__get_adapters_set(df)
        if adapter_set and (adapter_1_set or adapter_2_set or adapter_3_set or adapter_4_set):
            self.file.errors = ("Specify column 'adapter' or 'adpater_1/2/3/4', not both.",)
            validated = False

        if not adapter_set and not (adapter_1_set or adapter_2_set or adapter_3_set or adapter_4_set):
            df["adapter"] = "adapter_"
            df["adapter"] = df["adapter"] + (df.reset_index(drop=True).index + 1).astype(str)
            adapter_set = True

        if adapter_set:
            df["adapter_1"] = df["adapter"]
            df["adapter_2"] = df["adapter"]
            df["adapter_3"] = df["adapter"]
            df["adapter_4"] = df["adapter"]

        df = df.drop(columns=["adapter"])

        df.loc[~pd.isna(df["index_1"]), "index_1"] = df.loc[~pd.isna(df["index_1"]), "index_1"].str.strip()
        df.loc[~pd.isna(df["index_2"]), "index_2"] = df.loc[~pd.isna(df["index_2"]), "index_2"].str.strip()
        df.loc[~pd.isna(df["index_3"]), "index_3"] = df.loc[~pd.isna(df["index_3"]), "index_3"].str.strip()
        df.loc[~pd.isna(df["index_4"]), "index_4"] = df.loc[~pd.isna(df["index_4"]), "index_4"].str.strip()
        
        df["adapter_1"] = df["adapter_1"].str.strip()
        df["adapter_2"] = df["adapter_2"].str.strip()
        df["adapter_3"] = df["adapter_3"].str.strip()
        df["adapter_4"] = df["adapter_4"].str.strip()

        logger.debug(df)
            
        return validated, self, df

    def __get_adapters_set(self, df: pd.DataFrame) -> tuple[bool, bool, bool, bool, bool]:
        return (
            (~df["adapter"].isna()).any() if "adapter" in df.columns else False,
            (~df["adapter_1"].isna()).any() if "adapter_1" in df.columns else False,
            (~df["adapter_2"].isna()).any() if "adapter_2" in df.columns else False,
            (~df["adapter_3"].isna()).any() if "adapter_3" in df.columns else False,
            (~df["adapter_4"].isna()).any() if "adapter_4" in df.columns else False,
        )