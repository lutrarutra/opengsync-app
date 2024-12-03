import json
import uuid
import string
from typing import Optional, Literal, Any, Type, Callable

import pandas as pd
import numpy as np

from wtforms import StringField
from wtforms.validators import DataRequired
from flask_wtf import FlaskForm

from .. import logger
from ..tools import SpreadSheetColumn


class SpreadsheetInput(FlaskForm):
    spreadsheet = StringField("Spreadsheet", validators=[DataRequired()])

    colors = {
        "missing_value": "#FAD7A0",
        "invalid_value": "#F5B7B1",
        "duplicate_value": "#D7BDE2",
        "invalid_input": "#AED6F1"
    }

    def __init__(
        self, columns: list[SpreadSheetColumn], post_url: str, csrf_token: Optional[str],
        df: Optional[pd.DataFrame] = None, formdata: Optional[dict] = None,
        allow_new_rows: bool = False, allow_new_cols: bool = False,
        allow_col_rename: bool = False, min_spare_rows: int = 10,
    ):
        super().__init__(formdata=formdata)
        self.columns: dict[str, SpreadSheetColumn] = {}
        for col in columns:
            self.add_column(
                label=col.label,
                name=col.name,
                type=col.type,
                width=col.width,
                var_type=col.var_type,
                source=col.source,
                clean_up_fnc=col.clean_up_fnc
            )

        self.style: dict[str, str] = {}
        self._errors: list[str] = []
        self.post_url = post_url
        self.csrf_token = csrf_token
        self.id = uuid.uuid4().hex
        self.allow_new_rows = "true" if allow_new_rows else "false"
        self.allow_new_cols = "true" if allow_new_cols else "false"
        self.allow_col_rename = "true" if allow_col_rename else "false"
        self.min_spare_rows = min_spare_rows if allow_new_rows else 0
        self.col_names = formdata.get("columns") if formdata is not None else None
        if self.col_names is not None:
            self.col_names = json.loads(self.col_names).split(",")
        
        self.col_title_map = dict([(col.name, col.label) for col in self.columns.values()])

        if df is not None:
            _df = df.copy()
            for col in self.columns.keys():
                if col not in _df.columns:
                    _df[col] = None
                
            self._data = _df[self.columns.keys()].replace(np.nan, "").values.tolist()

        if formdata is not None and (data := formdata.get("spreadsheet")) is not None:
            self._data = json.loads(data)

        self.__df = df

    def add_column(
        self, label: str, name: str,
        type: Literal["text", "numeric", "dropdown"],
        width: float, var_type: Type,
        source: Optional[Any] = None,
        clean_up_fnc: Optional[Callable] = None,
    ):
        if label in self.columns.keys():
            raise ValueError(f"Column with label '{label}' already exists.")
        self.columns[label] = SpreadSheetColumn(
            letter=string.ascii_uppercase[len(self.columns)],
            label=label,
            name=name,
            type=type,
            width=width,
            var_type=var_type,
            source=source,
            clean_up_fnc=clean_up_fnc
        )

    def validate(self) -> bool:
        if not super().validate():
            self._errors = list(self.spreadsheet.errors)
            return False
        
        if self.col_names is None:
            logger.error("No column names provided in the request form.")
            raise ValueError("No column names provided in the request form.")
        
        if self.spreadsheet.data is None:
            self._errors = ["Spreadsheet is empty."]
            return False

        data = json.loads(self.spreadsheet.data)

        try:
            self.__df = pd.DataFrame(data)
        except ValueError as e:
            self.spreadsheet.errors = (f"Invalid Input: {e}",)
            return False
        
        self.__df = self.__df.replace(r'^\s*$', None, regex=True)
        self.__df.columns = [self.col_title_map[col_name] if col_name in self.col_title_map else col_name.lower().replace(" ", "_") for col_name in self.col_names]
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
        self.style[f"{self.columns[column].letter}{row_num}"] = f"background-color: {SpreadsheetInput.colors[color]};"
        message = f"Row {row_num}: {message}"
        if message not in self._errors:
            self._errors.append(message)

    def add_general_error(self, message: str):
        if message not in self._errors:
            self._errors.append(message)

    def labels(self) -> list[str]:
        return list(self.columns.keys())