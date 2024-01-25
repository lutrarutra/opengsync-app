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
        
        reused_barcodes = (df[["index_1", "index_2", "index_3", "index_4"]].duplicated(keep=False)) & (~df[["index_1", "index_2", "index_3", "index_4"]].isna().all(axis=1))

        for i, row in df.iterrows():
            # Check if sample names are unique in project
            _data = {
                "id": row["id"],
                "name": row["sample_name"],
                "library_type": row["library_type"],
                "error": None,
                "warning": "",
                "info": "",
                "index_1": row["index_1"],
                "index_2": row["index_2"],
                "index_3": row["index_3"],
                "index_4": row["index_4"],
                "adapter": row["adapter"],
            }

            if _data["index_1"] == _data["index_2"]:
                _data["warning"] += "Index 1 and index 2 are the same. "

            if _data["index_1"] == _data["index_3"]:
                _data["warning"] += "Index 1 and index 3 are the same. "

            if _data["index_1"] == _data["index_4"]:
                _data["warning"] += "Index 1 and index 4 are the same. "

            if _data["index_2"] == _data["index_3"]:
                _data["warning"] += "Index 2 and index 3 are the same. "

            if _data["index_2"] == _data["index_4"]:
                _data["warning"] += "Index 2 and index 4 are the same. "

            if _data["index_3"] == _data["index_4"]:
                _data["warning"] += "Index 3 and index 4 are the same. "

            if reused_barcodes[i]:
                _data["warning"] += "Index combination is reused in two or more libraries. "

            samples_data.append(_data)

        data["library_table"] = df
        self.update_data(data)

        return {
            "samples_data": samples_data,
            "show_index_1": df["index_1"].notnull().any(),
            "show_index_2": df["index_2"].notnull().any(),
            "show_index_3": df["index_3"].notnull().any(),
            "show_index_4": df["index_4"].notnull().any(),
        }
    
    def parse(self) -> dict[str, pd.DataFrame]:
        data = self.data
            
        return data
        
    def custom_validate(self):
        validated = self.validate()
        if not validated:
            return False, self

        return validated, self