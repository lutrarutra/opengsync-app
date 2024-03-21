from typing import Optional, Literal, Any
from dataclasses import dataclass

from flask import Response
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


class ConfirmRatiosForm(HTMXFlaskForm, TableDataForm):
    _template_path = "workflows/lane_pools/lp-3.html"
    _form_label = "confirm_ratios_form"

    spreadsheet_dummy = StringField(validators=[OptionalValidator()])

    def __init__(self, uuid: Optional[str] = None, formdata: dict = {}):
        if uuid is None:
            uuid = formdata.get("file_uuid")
        HTMXFlaskForm.__init__(self, formdata=formdata)
        TableDataForm.__init__(self, "lane_pools", uuid=uuid)

    def prepare(self, data: dict[str, pd.DataFrame | dict]) -> dict:
        df: pd.DataFrame = data["ratios_table"]  # type: ignore

        dilution_idx = df["volume"].notna() & df["qbit_after_dilution"].notna()

        df["conc"] = df["qbit"] / (df["fragment_size"] * 660) * 1_000_000
        
        df["eb_tween"] = None
        df.loc[dilution_idx, "eb_tween"] = (
            df.loc[dilution_idx, "conc"] * df.loc[dilution_idx, "volume"] * 0.5
        ) - df.loc[dilution_idx, "volume"]

        df["conc_after_dil"] = None
        df.loc[dilution_idx, "conc_after_dil"] = (
            df.loc[dilution_idx, "qbit_after_dilution"] / (df.loc[dilution_idx, "fragment_size"] * 660) * 1_000_000
        )

        df["share"] = None
        for _, _df in df.groupby("lane"):
            df.loc[_df.index, "share"] = _df["pool_reads_requested"] / _df["pool_reads_requested"].sum()

        df["pipet"] = 3.0 / df["fragment_size"] * df["share"] * 60.0
        data["ratios_table"] = df
        self.update_data(data)
        return { "df": df.replace(np.nan, "", regex=False), "enumerate": enumerate }
    
    
    def validate(self) -> bool:
        if not super().validate():
            return False
            
        return True
    
    def process_request(self, **context) -> Response:
        if not self.validate():
            return self.make_response(**context)
        
        data = self.get_data()
        raise NotImplementedError()
        



    