from uuid6 import uuid7

import pandas as pd


from .spreadsheet import SpreadSheetColumn
from ...core.templates import render_template

def format_with_space(n):
    return f"{n:,}".replace(",", " ")


class StaticSpreadsheet():
    def __init__(
        self, df: pd.DataFrame,
        columns: list[SpreadSheetColumn],
        style: dict[str, str] = {},
        id: str = uuid7().__str__(),
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

    async def render(self, **kwargs) -> str:
        return await render_template("components/static-spreadsheet.html", spreadsheet=self, **kwargs)