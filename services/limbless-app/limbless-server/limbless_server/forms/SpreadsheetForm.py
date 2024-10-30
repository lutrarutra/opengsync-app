from typing import Optional

import pandas as pd
import numpy as np

from flask import Response
from wtforms import StringField
from wtforms.validators import DataRequired

from .HTMXFlaskForm import HTMXFlaskForm
from ..tools import SpreadSheetColumn, tools


class SpreadsheetForm(HTMXFlaskForm):
    spreadsheet = StringField("Spreadsheet", validators=[DataRequired()])

    def __init__(self, columns: dict[str, SpreadSheetColumn], data: Optional[pd.DataFrame] = None, formdata: Optional[dict] = None):
        super().__init__(formdata=formdata)
        self.columns = columns
        self._context["columns"] = columns
        if data is not None:
            self._context["spreadsheet_data"] = data.replace(np.nan, "").values.tolist()

    def validate(self) -> bool:
        if not super().validate():
            return False

        return True