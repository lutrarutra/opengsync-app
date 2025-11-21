from uuid_extensions import uuid7str

import pandas as pd


from .spread_sheet_components import SpreadSheetColumn


class StaticSpreadSheet():
    def __init__(
        self, df: pd.DataFrame,
        columns: list[SpreadSheetColumn],
        style: dict[str, str] = {},
        id: str = uuid7str()
    ):
        self.__df = df.copy().round(3)
        self.columns = columns
        self.style = style
        self._id = id
        self._data = self.__df[[col.label for col in self.columns]].astype(object).replace(pd.NA, "").values.tolist()