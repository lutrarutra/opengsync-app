from typing import Optional, Literal, Any
from dataclasses import dataclass

import pandas as pd
import numpy as np

from wtforms import StringField
from wtforms.validators import Optional as OptionalValidator

from limbless_db import models

from ...HTMXFlaskForm import HTMXFlaskForm
from ...TableDataForm import TableDataForm


@dataclass
class SpreadSheetColumn:
    column: str
    label: str
    name: str
    type: Literal["text", "numeric", "dropdown"]
    width: float
    source: Optional[Any] = None
    bg_color: Optional[str] = None


colors = {
    "do_not_change": "#FADBD8",
    "required": "#E8DAEF",
    "optional": "#FCF3CF",
    "overwritable": "#D5F5E3",
}


columns = {
    "id": SpreadSheetColumn("A", "pool_id", "ID", "text", 60, bg_color=colors["do_not_change"]),
    "name": SpreadSheetColumn("B", "pool_name", "Pool Name", "text", 150, bg_color=colors["do_not_change"]),
    "fragment_size": SpreadSheetColumn("C", "fragment_size", "Fragment Size", "numeric", 120, bg_color=colors["required"]),
    "qbit": SpreadSheetColumn("D", "qbit", "Qbit", "numeric", 100, bg_color=colors["required"]),
    "volume": SpreadSheetColumn("E", "volume", "Volume", "numeric", 100, bg_color=colors["optional"]),
    "qbit_after_dilution": SpreadSheetColumn("F", "qbit_after_dilution", "Qbit After Dilution", "numeric", 150, bg_color=colors["optional"]),
    "m_reads": SpreadSheetColumn("G", "m_reads", "M Reads", "numeric", 100, bg_color=colors["overwritable"]),
}

errors = {
    "missing_value": "background-color: #FAD7A0;",
    "invalid_value": "background-color: #F5B7B1;",
    "duplicate_value": "background-color: #D7BDE2;",
    "ok": "background-color: #82E0AA;"
}


class PoolingRatioForm(HTMXFlaskForm, TableDataForm):
    _template_path = "workflows/lane_pools/lp-3.html"
    _form_label = "lane_pooling_form"

    spreadsheet_dummy = StringField(validators=[OptionalValidator()])

    def __init__(self, experiment: models.Experiment, formdata: Optional[dict] = None):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        TableDataForm.__init__(self, uuid=None)
        self.experiment = experiment
        self._context["experiment"] = experiment

    def prepare(self, data: Optional[dict[str, pd.DataFrame | dict]] = None) -> dict:
        if data is None:
            data = self.get_data()

        pool_table: pd.DataFrame = data["pool_table"]  # type: ignore

        spreadsheet_style = {}

        pooling_table = pool_table.copy()
        for key, value in columns.items():
            if key not in pooling_table.columns:
                pooling_table[key] = None

            if value.bg_color is None:
                continue
            
            for i in range(len(pooling_table)):
                spreadsheet_style[f"{value.column}{i + 1}"] = f"background-color: {value.bg_color};"

        spreadsheet_data = pooling_table[columns.keys()].replace(np.nan, "", regex=False).values.tolist()
        
        return {
            "spreadsheet_data": spreadsheet_data,
            "spreadsheet_columns": columns.values(),
            "spreadsheet_style": spreadsheet_style,
            "colors": colors
        }
    