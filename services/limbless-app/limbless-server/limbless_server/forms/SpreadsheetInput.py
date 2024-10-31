import json
import uuid
from typing import Optional, Literal

import pandas as pd
import numpy as np

from wtforms import StringField
from wtforms.validators import DataRequired

from ..tools import SpreadSheetColumn
from flask_wtf import FlaskForm


class SpreadsheetInput(FlaskForm):
    spreadsheet = StringField("Spreadsheet", validators=[DataRequired()])

    colors = {
        "missing_value": "#FAD7A0",
        "invalid_value": "#F5B7B1",
        "duplicate_value": "#D7BDE2",
        "invalid_input": "#AED6F1"
    }

    def __init__(
        self, columns: dict[str, SpreadSheetColumn], post_url: str, csrf_token: Optional[str],
        df: Optional[pd.DataFrame] = None, formdata: Optional[dict] = None,
        allow_new_rows: bool = False, allow_new_cols: bool = False,
        allow_col_rename: bool = False, min_spare_rows: int = 10,
    ):
        super().__init__(formdata=formdata)
        self.columns = columns
        self.style: dict[str, str] = {}
        self._errors: list[str] = []
        self.post_url = post_url
        self.csrf_token = csrf_token
        self.id = str(uuid.uuid4())
        self.allow_new_rows = "true" if allow_new_rows else "false"
        self.allow_new_cols = "true" if allow_new_cols else "false"
        self.allow_col_rename = "true" if allow_col_rename else "false"
        self.min_spare_rows = min_spare_rows if allow_new_rows else 0

        if df is not None:
            self._data = df.replace(np.nan, "").values.tolist()

        if formdata is not None and (data := formdata.get("spreadsheet")) is not None:
            self._data = json.loads(data)

        self.__df = df

    def validate(self) -> bool:
        if not super().validate():
            self._errors = list(self.spreadsheet.errors)
            return False
        
        if self.spreadsheet.data is None:
            self._errors = ["Spreadsheet is empty."]
            return False

        data = json.loads(self.spreadsheet.data)

        try:
            self.__df = pd.DataFrame(data)
        except ValueError as e:
            self.spreadsheet.errors = (f"Invalid Input: {e}",)
            return False
        
        self.__df.columns = list(self.columns.keys())
        self.__df = self.__df.replace(r'^\s*$', None, regex=True)
        self.__df = self.__df.dropna(how="all")

        for label, column in self.columns.items():
            if column.clean_up_fnc is not None:
                self.__df[label] = self.__df[label].apply(column.clean_up_fnc)

        if len(self.__df) == 0:
            self._errors = ["Spreadsheet is empty.",]
            return False
        
        self._data = self.__df.replace(np.nan, "").values.tolist()

        return True
    
    @property
    def df(self) -> pd.DataFrame:
        if self.__df is None:
            raise ValueError("Form not validated")
        return self.__df.copy()
    
    def add_error(
        self, row_num: int, column: str, message: str,
        color: Literal["missing_value", "invalid_value", "duplicate_value", "invalid_input"]
    ):
        self.style[f"{self.columns[column].column}{row_num}"] = f"background-color: {SpreadsheetInput.colors[color]};"
        message = f"Row {row_num}: {message}"
        if message not in self._errors:
            self._errors.append(message)