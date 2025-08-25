import json
from uuid_extensions import uuid7str
import string
from typing import Optional, Hashable

import pandas as pd
import numpy as np

from wtforms import StringField
from wtforms.validators import DataRequired
from flask_wtf import FlaskForm

from .. import logger
from ..tools.spread_sheet_components import SpreadSheetColumn, SpreadSheetException, DropdownColumn


class SpreadsheetInput(FlaskForm):
    spreadsheet = StringField("Spreadsheet", validators=[DataRequired()])

    def __init__(
        self, columns: list[SpreadSheetColumn], post_url: str, csrf_token: Optional[str],
        df: Optional[pd.DataFrame] = None, formdata: Optional[dict] = None,
        allow_new_rows: bool = False, allow_new_cols: bool = False,
        allow_col_rename: bool = False, min_spare_rows: int = 10,
    ):
        super().__init__(formdata=formdata)
        self.columns: dict[str, SpreadSheetColumn] = {}
        for col in columns:
            col.letter = string.ascii_uppercase[len(self.columns)]
            self.add_column(col.label, col)

        self.style: dict[str, str] = {}
        self._errors: list[str] = []
        self.post_url = post_url
        self.csrf_token = csrf_token
        self.id = uuid7str()
        self.allow_new_rows = "true" if allow_new_rows else "false"
        self.allow_new_cols = "true" if allow_new_cols else "false"
        self.allow_col_rename = "true" if allow_col_rename else "false"
        self.min_spare_rows = min_spare_rows if allow_new_rows else 0
        self.col_names = formdata.get("columns") if formdata is not None else None
        if self.col_names is not None:
            self.col_names = json.loads(self.col_names).split(",")
        
        self.col_title_map = dict([(col.name, col.label) for col in self.columns.values()])

        if df is not None:
            self.set_data(df)

        if formdata is not None and (data := formdata.get("spreadsheet")) is not None:
            self._data = json.loads(data)

    def set_data(self, data: pd.DataFrame):
        _df = data.copy()
        for col in self.columns.keys():
            if col not in _df.columns:
                _df[col] = None
            
        self._data = _df[self.columns.keys()].replace(np.nan, "").values.tolist()
        self.__df = _df

    def add_column(self, label: str, column: SpreadSheetColumn):
        if label in self.columns.keys():
            raise ValueError(f"Column with label '{label}' already exists.")
        self.columns[label] = column

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
        
        self.__df = self.__df.replace(r'^\s*$', None, regex=True).map(lambda x: x.replace('\x00', '').strip() if isinstance(x, str) else x).copy()
        self.__df.columns = [self.col_title_map[col_name] if col_name in self.col_title_map else col_name.lower().replace(" ", "_") for col_name in self.col_names]
        self.__df = self.__df.dropna(how="all")

        if len(self.__df) == 0:
            self._errors = ["Spreadsheet is empty.",]
            return False
        
        for label, column in self.columns.items():
            if isinstance(column, DropdownColumn):
                if column.all_options_required:
                    if column.source is None:
                        raise ValueError(f"Column '{label}' has no choices defined.")
                    for opt in column.source:
                        if opt not in self.__df[label].unique():
                            self.add_general_error(f"Column '{label}' has missing option '{opt}'. You must use all options atleast once.")

        for idx, row in self.__df.iterrows():
            for label, column in self.columns.items():
                try:
                    column.validate(row[label], column_values=self.__df[label].tolist())
                except SpreadSheetException as e:
                    if column.required and pd.isna(row[label]):
                        self.add_error(idx, label, e)
                    elif column.type == "dropdown" and row[label] not in column.source:
                        if column.source is None:
                            logger.error(f"Column '{label}' has no choices defined.")
                            raise ValueError(f"Column '{label}' has no choices defined.")
                        self.add_error(idx, label, e)
                    else:
                        self.add_error(idx, label, e)
                    continue
                    
                self.__df.at[idx, label] = column.clean_up(row[label])
        
        self._data = self.__df.replace(np.nan, "").values.tolist()

        if len(self._errors) > 0:
            return False

        return True
    
    @property
    def df(self) -> pd.DataFrame:
        if self.__df is None:
            raise ValueError("Form not validated")
        return self.__df.copy()
    
    def add_error(self, idx: Hashable, column: str | list[str], exception: SpreadSheetException):
        message = exception.message
        row_num = self.df.index.get_loc(idx) + 1  # type: ignore
        if isinstance(column, str):
            column = [column]
        for col in column:
            self.style[f"{self.columns[col].letter}{row_num}"] = f"background-color: {exception.color};"
        message = f"Row {row_num}: {message}"
        if message not in self._errors:
            self._errors.append(message)

    def add_general_error(self, message: str):
        if message not in self._errors:
            self._errors.append(message)

    def labels(self) -> list[str]:
        return list(self.columns.keys())