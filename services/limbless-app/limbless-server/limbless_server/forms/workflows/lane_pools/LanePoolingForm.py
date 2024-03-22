from typing import Optional, Literal, Any
from dataclasses import dataclass

import pandas as pd
import numpy as np

from flask import Response
from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, FieldList, FormField
from wtforms.validators import Optional as OptionalValidator, DataRequired

from ...HTMXFlaskForm import HTMXFlaskForm
from ...TableDataForm import TableDataForm


class PoolQCSubForm(FlaskForm):
    m_reads = FloatField(validators=[DataRequired()])


class LanePoolingForm(HTMXFlaskForm, TableDataForm):
    _template_path = "workflows/lane_pools/lp-3.html"
    _form_label = "lane_pooling_form"

    spreadsheet_dummy = StringField(validators=[OptionalValidator()])
    input_fields = FieldList(FormField(PoolQCSubForm), min_entries=1)

    def __init__(self, uuid: Optional[str] = None, formdata: dict = {}):
        if uuid is None:
            uuid = formdata.get("file_uuid")
        HTMXFlaskForm.__init__(self, formdata=formdata)
        TableDataForm.__init__(self, "lane_pools", uuid=uuid)

    def prepare(self, data: dict[str, pd.DataFrame | dict]) -> dict:
        df: pd.DataFrame = data["lane_table"]  # type: ignore

        for i, (_, row) in enumerate(df.iterrows()):
            if i > len(self.input_fields) - 1:
                self.input_fields.append_entry()

            entry = self.input_fields[i]
            entry.m_reads.data = row["pool_reads_requested"]

        dilution_idx = df["volume"].notna() & df["qbit_after_dilution"].notna()
        
        # https://knowledge.illumina.com/library-preparation/dna-library-prep/library-preparation-dna-library-prep-reference_material-list/000001240
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
        return {"df": df, "enumerate": enumerate}
    
    def validate(self) -> bool:
        if not super().validate():
            return False
            
        return True
    
    def process_request(self, **context) -> Response:
        if not self.validate():
            return self.make_response(**context)
        
        data = self.get_data()
        raise NotImplementedError()
        



    