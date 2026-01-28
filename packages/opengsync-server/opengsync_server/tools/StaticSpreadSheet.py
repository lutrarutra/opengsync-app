from uuid_extensions import uuid7str

import pandas as pd


from .spread_sheet_components import SpreadSheetColumn

def format_with_space(n):
    return f"{n:,}".replace(",", " ")


class StaticSpreadSheet():
    def __init__(
        self, df: pd.DataFrame,
        columns: list[SpreadSheetColumn],
        style: dict[str, str] = {},
        id: str = uuid7str(),
        format_big_numbers: bool = True,
    ):
        self.__df = df.copy().round(3)
        self.columns = columns
        self.style = style
        self._id = id
        if format_big_numbers:
            for col in self.__df.select_dtypes(include=["int64", "float64"]).columns:
                self.__df[col] = self.__df[col].apply(format_with_space)
                self.__df[col] = self.__df[col].replace("nan", "")

        self._data = self.__df[[col.label for col in self.columns]].astype(object).replace(pd.NA, "").values.tolist()