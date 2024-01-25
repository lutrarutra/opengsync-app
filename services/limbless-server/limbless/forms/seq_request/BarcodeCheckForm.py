from typing import Optional
import pandas as pd

from wtforms import TextAreaField, BooleanField
from wtforms.validators import DataRequired, Optional as OptionalValidator

from ... import db, models, logger
from .TableDataForm import TableDataForm


# 7. Check barcodes
class BarcodeCheckForm(TableDataForm):
    reverse_complement_index_1 = BooleanField("Reverse complement index 1", default=False)
    reverse_complement_index_2 = BooleanField("Reverse complement index 2", default=False)
    reverse_complement_index_3 = BooleanField("Reverse complement index 3", default=False)
    reverse_complement_index_4 = BooleanField("Reverse complement index 4", default=False)
    
    def prepare(self, data: Optional[dict[str, pd.DataFrame]] = None) -> dict:
        if data is None:
            data = self.data

        df = data["library_table"]

        samples_data: list[dict[str, str | int | None]] = []

        indices_present = []
        if "index_1" in df.columns:
            indices_present.append("index_1")
        if "index_2" in df.columns:
            indices_present.append("index_2")
        if "index_3" in df.columns:
            indices_present.append("index_3")
        if "index_4" in df.columns:
            indices_present.append("index_4")
        
        reused_barcodes = (df[indices_present].duplicated(keep=False)) & (~df[indices_present].isna().all(axis=1))

        for i, row in df.iterrows():
            # Check if sample names are unique in project
            _data = {
                "id": row["id"],
                "name": row["sample_name"],
                "library_type": row["library_type"],
                "error": None,
                "warning": "",
                "info": "",
            }
            if "index_1" in row:
                _data["index_1"] = row["index_1"]
            
            if "index_2" in row:
                _data["index_2"] = row["index_2"]

            if "index_3" in row:
                _data["index_3"] = row["index_3"]

            if "index_4" in row:
                _data["index_4"] = row["index_4"]

            if "adapter" in row:
                _data["adapter"] = row["adapter"]

            if reused_barcodes[i]:
                _data["warning"] += "Index combination is reused in two or more libraries. "

            samples_data.append(_data)

        data["library_table"] = df
        self.update_data(data)

        return {
            "samples_data": samples_data,
            "show_index_1": "index_1" in df.columns,
            "show_index_2": "index_2" in df.columns,
            "show_index_3": "index_3" in df.columns,
            "show_index_4": "index_4" in df.columns,
        }
    
    def parse(self) -> dict[str, pd.DataFrame]:
        data = self.data
            
        return data
        
    def custom_validate(self):
        validated = self.validate()
        if not validated:
            return False, self

        return validated, self