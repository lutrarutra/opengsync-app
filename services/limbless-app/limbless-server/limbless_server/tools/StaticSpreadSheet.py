from uuid import uuid4

import pandas as pd


from .spread_sheet_components import SpreadSheetColumn


class StaticSpreadSheet():
    def __init__(
        self, df: pd.DataFrame,
        columns: list[SpreadSheetColumn],
        style: dict[str, str] = {},
        id: str = uuid4().hex
    ):
        self.__df = df
        self.columns = columns
        self.style = style
        self._id = id
        self._data = self.__df[[col.label for col in self.columns]].replace(pd.NA, "").values.tolist()