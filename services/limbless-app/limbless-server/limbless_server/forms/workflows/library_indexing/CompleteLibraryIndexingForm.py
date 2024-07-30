import os
from typing import Optional

import pandas as pd
import openpyxl
from openpyxl.utils import get_column_letter

from flask import Response, url_for, flash, current_app
from flask_htmx import make_response

from limbless_db import models

from .... import logger, db, tools
from ...TableDataForm import TableDataForm
from ...HTMXFlaskForm import HTMXFlaskForm


class CompleteLibraryIndexingForm(HTMXFlaskForm, TableDataForm):
    _template_path = "workflows/library_indexing/indexing-3.html"
    _form_label = "library_indexing_form"

    def __init__(self, previous_form: Optional[TableDataForm] = None, formdata: dict = {}, uuid: Optional[str] = None):
        if uuid is None:
            uuid = formdata.get("file_uuid")
        HTMXFlaskForm.__init__(self, formdata=formdata)
        TableDataForm.__init__(self, dirname="library_indexing", uuid=uuid, previous_form=previous_form)

    def prepare(self):
        barcode_table = self.tables["barcode_table"]

        barcode_table = tools.check_indices(barcode_table, groupby="pool")

        self._context["barcode_table"] = barcode_table

    def validate(self) -> bool:
        validated = super().validate()
        return validated

    def process_request(self, user: models.User) -> Response:
        if not self.validate():
            return self.make_response()
        
        barcode_table = self.tables["barcode_table"]
        
        if (lab_prep_id := self.metadata.get("lab_prep_id")) is None:
            logger.error(f"{self.uuid}: LabPrep id not found")
            raise ValueError(f"{self.uuid}: LabPrep id not found")
        
        if (lab_prep := db.get_lab_prep(lab_prep_id)) is None:
            logger.error(f"{self.uuid}: LabPrep not found")
            raise ValueError(f"{self.uuid}: LabPrep not found")
        
        if lab_prep.prep_file is not None:
            wb = openpyxl.load_workbook(os.path.join(current_app.config["MEDIA_FOLDER"], lab_prep.prep_file.path))
            active_sheet = wb["prep_table"]
            prep_table = pd.DataFrame(active_sheet.values)
            prep_table.columns = prep_table.iloc[0]
            prep_table = prep_table.drop(0)
            prep_table = prep_table.drop(prep_table[prep_table["library_id"].isna()].index)
            
            column_mapping: dict[str, str] = {}
            for col_i in range(1, active_sheet.max_column):
                col = get_column_letter(col_i + 1)
                column_name = active_sheet[f"{col}1"].value
                column_mapping[column_name] = col
            
            for i, (idx, row) in enumerate(prep_table.iterrows()):
                if (library := db.get_library(row["library_id"])) is None:
                    logger.error(f"{self.uuid}: Library {row['library_id']} not found")
                    raise ValueError(f"{self.uuid}: Library {row['library_id']} not found")
                
                library = db.remove_library_indices(library.id)

                df = barcode_table[barcode_table["library_id"] == row["library_id"]].copy()
                for j in range(len(df["sequence_i7"].values)):
                    library = db.add_library_index(
                        library_id=library.id,
                        name_i7=row["name_i7"],
                        name_i5=row["name_i5"],
                        sequence_i7=df["sequence_i7"].values[j],
                        sequence_i5=df["sequence_i5"].values[j] if len(df["sequence_i5"].values) > j else None,
                    )

                sequence_i7 = ";".join(df["sequence_i7"].values)
                sequence_i5 = ";".join(df["sequence_i5"].values)
                active_sheet[f"{column_mapping['sequence_i7']}{i + 2}"].value = sequence_i7
                active_sheet[f"{column_mapping['sequence_i5']}{i + 2}"].value = sequence_i5

            wb.save(os.path.join(current_app.config["MEDIA_FOLDER"], lab_prep.prep_file.path))

        flash("Library Indexing completed!", "success")
        return make_response(redirect=url_for("lab_preps_page.lab_prep_page", lab_prep_id=lab_prep.id))
