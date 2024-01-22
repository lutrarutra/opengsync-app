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

    def prepare(self, data: Optional[dict[str, pd.DataFrame]] = None) -> dict:
        if data is None:
            data = self.data

        df = data["sample_table"]

        libraries: list[dict[str, str | int | None]] = []

        for i, row in df.iterrows():
            # Check if sample names are unique in project
            _data = {
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
                _data["info"] = "Existing sample found from project."
            else:
                _data["info"] = "New sample."

            libraries.append(_data)

        selected_samples = []
        for sample_data in libraries:
            if sample_data["error"] is None:
                selected_samples.append(sample_data["id"])
        self.selected_libraries.data = ",".join([str(i) for i in selected_samples])

        data["sample_table"] = df
        self.update_data(data)

        return {
            "libraries": libraries,
        }
    
    def parse(self) -> dict[str, pd.DataFrame]:
        if self.selected_libraries.data is None:
            assert False    # This should never happen because its checked in custom_validate()

        data = self.data
        df = data["sample_table"]

        selected_libraries_ids = self.selected_libraries.data.removeprefix(",").split(",")
        selected_libraries_ids = [int(i) - 1 for i in selected_libraries_ids if i != ""]

        df = df.loc[selected_libraries_ids, :].reset_index()

        data["sample_table"] = df
        self.update_data(data)

        return data

    def custom_validate(self):
        validated = self.validate()
        if not validated:
            return False, self
        
        if self.selected_libraries.data is None or len(self.selected_libraries.data) == 0:
            self.selected_libraries.errors = ("Please select at least one sample.",)
            validated = False

        return validated, self
