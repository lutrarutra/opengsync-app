from typing import Optional
from io import StringIO
import pandas as pd

from wtforms import StringField, SelectField, FieldList, FormField, TextAreaField, IntegerField, BooleanField
from wtforms.validators import DataRequired, Length, Optional as OptionalValidator

from ... import db, models
from ...core.DBHandler import DBHandler
from ...core.DBSession import DBSession
from .TableDataForm import TableDataForm


# 5. Confirm samples before creating
class SampleSelectForm(TableDataForm):
    selected_samples = StringField()

    def prepare(self, seq_request_id: int, df: Optional[pd.DataFrame] = None) -> dict:
        if df is None:
            df = self.get_df()

        samples: list[dict[str, str | int | None]] = []

        for i, row in df.iterrows():
            # Check if sample names are unique in project
            data = {
                "id": int(i) + 1,
                "name": row["sample_name"],
                "organism": row["organism"],
                "tax_id": row["tax_id"],
                "error": None,
                "info": "",
                "sample_id": int(row["sample_id"]) if not pd.isnull(row["sample_id"]) else None,
                "project_id": int(row["project_id"]) if not pd.isnull(row["project_id"]) else None,
                "project_name": row["project_name"],
                "index_1": row["index_1"],
                "index_2": row["index_2"],
                "adapter": row["adapter"],
            }

            if row["sample_id"] is not None:
                data["info"] = "Existing sample found from project."
            else:
                data["info"] = "New sample."

            samples.append(data)

        selected_samples = []
        for sample_data in samples:
            if sample_data["error"] is None:
                selected_samples.append(sample_data["id"])
        self.selected_samples.data = ",".join([str(i) for i in selected_samples])

        self.set_df(df)

        return {
            "samples": samples,
        }
    
    def parse(self) -> pd.DataFrame:
        if self.selected_samples.data is None:
            assert False    # This should never happen because its checked in custom_validate()

        df = self.get_df()
        selected_samples_ids = self.selected_samples.data.removeprefix(",").split(",")
        selected_samples_ids = [int(i) - 1 for i in selected_samples_ids if i != ""]

        df = df.loc[selected_samples_ids, :].reset_index()
        return df

    def custom_validate(self):
        validated = self.validate()
        if not validated:
            return False, self
        
        if self.selected_samples.data is None or len(self.selected_samples.data) == 0:
            self.selected_samples.errors = ("Please select at least one sample.",)
            validated = False

        return validated, self
