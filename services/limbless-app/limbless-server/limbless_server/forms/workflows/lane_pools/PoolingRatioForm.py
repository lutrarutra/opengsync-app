from typing import Optional, Literal, Any
from dataclasses import dataclass

from flask import Response
import pandas as pd
import numpy as np

from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, FloatField, FieldList, FormField
from wtforms.validators import Optional as OptionalValidator, DataRequired

from .ConfirmRatiosForm import ConfirmRatiosForm
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
    "pool_id": SpreadSheetColumn("A", "pool_id", "ID", "text", 60, bg_color=colors["do_not_change"]),
    "pool_name": SpreadSheetColumn("B", "pool_name", "Pool Name", "text", 150, bg_color=colors["do_not_change"]),
    "lane": SpreadSheetColumn("C", "lane", "Lane", "numeric", 80, bg_color=colors["do_not_change"]),
    "fragment_size": SpreadSheetColumn("D", "fragment_size", "Fragment Size", "numeric", 120, bg_color=colors["required"]),
    "qbit": SpreadSheetColumn("E", "qbit", "Qbit", "numeric", 100, bg_color=colors["required"]),
    "volume": SpreadSheetColumn("F", "volume", "Volume", "numeric", 100, bg_color=colors["optional"]),
    "qbit_after_dilution": SpreadSheetColumn("G", "qbit_after_dilution", "Qbit After Dilution", "numeric", 150, bg_color=colors["optional"]),
    "m_reads": SpreadSheetColumn("H", "m_reads", "M Reads", "numeric", 100, bg_color=colors["overwritable"]),
}


class PoolingRatioSubForm(FlaskForm):
    m_reads = FloatField(validators=[DataRequired()])
    fragment_size = IntegerField(validators=[DataRequired()])
    qbit = FloatField(validators=[DataRequired()])
    volume = FloatField(validators=[OptionalValidator()])
    qbit_after_dilution = FloatField( validators=[OptionalValidator()])



class PoolingRatioForm(HTMXFlaskForm, TableDataForm):
    _template_path = "workflows/lane_pools/lp-2.html"
    _form_label = "pooling_ratio_form"

    input_fields = FieldList(FormField(PoolingRatioSubForm), min_entries=1)
    target_concentration = FloatField("Target Concentration", default=3.0, validators=[DataRequired()])

    def __init__(self, uuid: Optional[str] = None, formdata: dict = {}):
        if uuid is None:
            uuid = formdata.get("file_uuid")
        HTMXFlaskForm.__init__(self, formdata=formdata)
        TableDataForm.__init__(self, "lane_pools", uuid=uuid)

    def __get_style(self, n_rows: int) -> dict:
        spreadsheet_style = {}
        for _, value in columns.items():
            if value.bg_color is None:
                continue
            
            for i in range(1, n_rows + 1):
                spreadsheet_style[f"{value.column}{i}"] = f"background-color: {value.bg_color};"

        return spreadsheet_style
        

    def prepare(self, data: Optional[dict[str, pd.DataFrame | dict]] = None) -> dict:
        if data is None:
            data = self.get_data()

        df: pd.DataFrame = data["pool_table"]  # type: ignore

        for i, (_, row) in enumerate(df.iterrows()):
            if i > len(self.input_fields) - 1:
                self.input_fields.append_entry()

            entry = self.input_fields[i]
            entry.m_reads.data = row["pool_reads_requested"]

        return { "df": df, "enumerate": enumerate }
    
    def validate(self) -> bool:
        if not super().validate():
            return False
        
        from .... import logger

        validated = True
        for i, entry in enumerate(self.input_fields):
            logger.debug(f"{entry.volume.data} {entry.qbit_after_dilution.data}")
            if entry.volume.data is None and entry.qbit_after_dilution.data is not None:
                entry.volume.errors = ("Volume is required if Qbit After Dilution is defined",)
                validated = False
            
            if entry.qbit_after_dilution.data is None and entry.volume.data is not None:
                entry.qbit_after_dilution.errors = ("Qbit After Dilution is required if Volume is defined",)
                validated = False
            
        return validated
    
    def process_request(self, **context) -> Response:
        data = self.get_data()
        df: pd.DataFrame = data["pool_table"]  # type: ignore
        if not self.validate():
            context["df"] = df
            context["enumerate"] = enumerate
            return self.make_response(**context)
        
        for i, entry in enumerate(self.input_fields):
            df.at[i, "fragment_size"] = entry.fragment_size.data
            df.at[i, "qbit"] = entry.qbit.data
            df.at[i, "volume"] = entry.volume.data
            df.at[i, "qbit_after_dilution"] = entry.qbit_after_dilution.data
            df.at[i, "pool_reads_requested"] = entry.m_reads.data

        df["fragment_size"] = df["fragment_size"].astype(int)

        data["ratios_table"] = df

        confirm_ratios_form = ConfirmRatiosForm(self.uuid)
        context = confirm_ratios_form.prepare(data) | context
        return confirm_ratios_form.make_response(**context)
        



    