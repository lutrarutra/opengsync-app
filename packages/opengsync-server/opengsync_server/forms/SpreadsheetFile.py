from uuid6 import uuid7
import string
from typing import Optional, Hashable

import pandas as pd

from flask_wtf import FlaskForm
from wtforms import FileField

from .. import logger
from ..tools.spread_sheet_components import TextColumn, FloatColumn, IntegerColumn, SpreadSheetColumn, SpreadSheetException, DropdownColumn, CategoricalDropDown


class SpreadsheetFile(FlaskForm):
    MAX_SIZE_MBYTES = 5
    
    file = FileField()

    def __init__(
        self, columns: list[SpreadSheetColumn], post_url: str, csrf_token: Optional[str],
        sheet_name: str | None = None, formdata: Optional[dict] = None,
    ):
        super().__init__(formdata=formdata)
        self.columns: dict[str, SpreadSheetColumn] = {}
        for col in columns:
            self.add_column(col.label, col)

        if sheet_name is not None:
            self._allowed_extensions = [
                ("xlsx", "Excel File"),
                ("tsv", "Tab-separated values"),
                ("csv", "Comma-separated values"),
            ]
        else:
            self._allowed_extensions = [
                ("tsv", "Tab-separated values"),
                ("csv", "Comma-separated values"),
            ]

        self.sheet_name = sheet_name
        self.post_url = post_url
        self.csrf_token = csrf_token
        self.id = uuid7().__str__()
        self._data = None
        self.col_title_map = dict([(col.name, col.label) for col in self.columns.values()])
        self.cell_errors: dict[str, list[tuple[int, str]]] = {}

    def set_data(self, data: pd.DataFrame):
        _df = data.copy()
        for col in self.columns.keys():
            if col not in _df.columns:
                _df[col] = None
            
        self.__df = _df

    def add_column(self, label: str, column: SpreadSheetColumn):
        if label in self.columns.keys():
            raise ValueError(f"Column with label '{label}' already exists.")
        self.columns[label] = column

    def validate(self) -> bool:
        if self.file.data is None:
            self.file.errors = ["File is required."]
            return False
        max_bytes = SpreadsheetFile.MAX_SIZE_MBYTES * 1024 * 1024
        size_bytes = len(self.file.data.read())
        self.file.data.seek(0)

        self.file.errors: list[str] = []  # type: ignore

        if size_bytes > max_bytes:
            self.file.errors = [f"File size exceeds {SpreadsheetFile.MAX_SIZE_MBYTES} MB"]
            return False
        
        ext = self.file.data.filename.split(".")[-1].lower()

        if ext == "xlsx" and self.sheet_name is None:
            self.file.errors = ["Unsupported file type. Allowed file types are: tsv and csv."]
            return False
        else:
            if ext not in ["tsv", "csv", "xlsx"]:
                self.file.errors = ["Unsupported file type. Allowed file types are: tsv, csv, and xlsx."]
                return False
        
        if not super().validate():
            self.file.errors = list(self.file.errors)
            return False
        
        if ext == "xlsx":
            self.__df: pd.DataFrame = pd.read_excel(self.file.data, sheet_name=self.sheet_name, dtype=None)  # type: ignore
            if isinstance(self.__df, dict):
                self.file.errors = [f"Multiple sheets with '{self.sheet_name}' name found in the file."]
                return False
        else:
            self.__df = pd.read_csv(self.file.data, sep="\t" if ext == "tsv" else ",", dtype=None)
        
        self.file.data.seek(0)

        if len(self.__df) == 0:
            self.file.errors = ["Spreadsheet is empty."]
            return False
        
        for label, column in self.columns.items():
            if column.label not in self.__df.columns:
                if not column.optional_col:
                    self.add_general_error(f"Column '{label}' is missing in the spreadsheet.")
                continue
            
            if isinstance(column, CategoricalDropDown):
                self.__df[label] = self.__df[label].astype(object)
            elif isinstance(column, TextColumn):
                self.__df[label] = self.__df[label].astype(str)
            elif isinstance(column, DropdownColumn):
                self.__df[label] = self.__df[label].astype(object)
            
            for idx, value in enumerate(self.__df[label].tolist()):
                try:
                    column.validate(value, column_values=self.__df[label].tolist())
                except SpreadSheetException as e:
                    if column.required and pd.isna(value):
                        self.add_error(idx, label, e)
                    elif column.type == "dropdown" and value not in column.source:
                        if column.source is None:
                            logger.error(f"Column '{label}' has no choices defined.")
                            raise ValueError(f"Column '{label}' has no choices defined.")
                        self.add_error(idx, label, e)
                    else:
                        self.add_error(idx, label, e)
                    continue
                    
                self.__df.at[idx, label] = column.clean_up(value)

        if len(self.errors) > 0:
            return False
        
        for label, column in self.columns.items():
            if label not in self.__df.columns:
                continue
            if isinstance(column, TextColumn):
                self.__df[label] = self.__df[label].astype(str)
            elif isinstance(column, IntegerColumn):
                self.__df[label] = self.__df[label].astype(pd.Int64Dtype())
            elif isinstance(column, FloatColumn):
                self.__df[label] = self.__df[label].astype(pd.Float64Dtype())

        return True
    
    @property
    def df(self) -> pd.DataFrame:
        if self.__df is None:
            raise ValueError("Form not validated")
        return self.__df.copy()
    
    @property
    def style(self) -> dict[str, str]:
        style = {}
        for i, e in enumerate(self.cell_errors.values()):
            letter = string.ascii_uppercase[i % 26]
            for row_num, color in e:
                style[f"{letter}{row_num}"] = f"background-color: {color};"

        logger.debug(style)
        return style
        
    def add_error(self, idx: Hashable, column: str | list[str], exception: SpreadSheetException):
        message = exception.message
        row_num: int = self.df.index.get_loc(idx) + 1  # type: ignore
        if isinstance(column, str):
            column = [column]

        for col in column:
            if col not in self.cell_errors:
                self.cell_errors[col] = []
            self.cell_errors[col].append((row_num, exception.color))

        message = f"Row {row_num}: {message}"
        if message not in self.file.errors:
            self.file.errors.append(message)  # type: ignore

    def add_general_error(self, message: str):
        if message not in self.file.errors:
            self.file.errors.append(message)  # type: ignore

    def labels(self) -> list[str]:
        return list(self.columns.keys())