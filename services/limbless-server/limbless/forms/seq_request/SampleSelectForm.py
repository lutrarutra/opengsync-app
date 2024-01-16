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
class LibrarySelectForm(TableDataForm):
    selected_libraries = StringField()

    def prepare(self, seq_request_id: int, df: Optional[pd.DataFrame] = None) -> dict:
        if df is None:
            df = self.get_df()

        libraries: list[dict[str, str | int | None]] = []

        for i, row in df.iterrows():
            # Check if sample names are unique in project
            data = {
                "id": int(i) + 1,
                "name": row["sample_name"],
                "library_type": row["library_type"],
                "organism": row["organism"],
                "tax_id": row["tax_id"],
                "error": None,
                "info": "",
                "sample_id": int(row["sample_id"]) if (not pd.isna(row["sample_id"]) and not pd.isnull(row["sample_id"])) else None,
                "project_id": int(row["project_id"]) if (not pd.isna(row["project_id"]) and not pd.isnull(row["project_id"])) else None,
                "project_name": row["project_name"],
                "index_1": row["index_1"],
                "index_2": row["index_2"],
                "adapter": row["adapter"],
                "pool": row["pool"],
            }

            if not pd.isna(row["sample_id"]):
                data["info"] = "Existing sample found from project."
            else:
                data["info"] = "New sample."

            libraries.append(data)

        selected_samples = []
        for sample_data in libraries:
            if sample_data["error"] is None:
                selected_samples.append(sample_data["id"])
        self.selected_libraries.data = ",".join([str(i) for i in selected_samples])

        self.set_df(df)

        return {
            "libraries": libraries,
        }
    
    def parse(self) -> pd.DataFrame:
        if self.selected_libraries.data is None:
            assert False    # This should never happen because its checked in custom_validate()

        df = self.get_df()
        selected_libraries_ids = self.selected_libraries.data.removeprefix(",").split(",")
        selected_libraries_ids = [int(i) - 1 for i in selected_libraries_ids if i != ""]

        df = df.loc[selected_libraries_ids, :].reset_index()
        return df

    def custom_validate(self):
        validated = self.validate()
        if not validated:
            return False, self
        
        if self.selected_libraries.data is None or len(self.selected_libraries.data) == 0:
            self.selected_libraries.errors = ("Please select at least one sample.",)
            validated = False

        return validated, self
