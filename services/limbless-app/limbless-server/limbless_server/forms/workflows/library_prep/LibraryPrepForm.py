import os
from uuid import uuid4

import pandas as pd

from flask import Response, current_app, url_for, flash
from flask_htmx import make_response

from limbless_db import models, to_utc
from limbless_db.categories import FileType

from .... import logger, db  # noqa F401
from .PrepTableForm import PrepTableForm


class LibraryPrepForm(PrepTableForm):
    def get_table(self) -> pd.DataFrame:
        if self.lab_prep.prep_file is not None:
            prep_table = pd.read_csv(os.path.join(current_app.config["MEDIA_FOLDER"], self.lab_prep.prep_file.path), sep="\t")
        else:
            if current_app.static_folder is None:
                raise ValueError("Static folder not set")
            prep_table = pd.read_csv(os.path.join(current_app.static_folder, "resources", "templates", "rna-prep.csv"), sep="\t")
            prep_table["sample_name"] = prep_table["sample_name"].astype(str).replace("nan", None)

        for library in self.lab_prep.libraries:
            if library.name not in prep_table["sample_name"].values:
                prep_table.loc[prep_table[prep_table["sample_name"].isna()].index[0], "sample_name"] = library.name

        return prep_table
    
    def validate(self) -> bool:
        max_bytes = LibraryPrepForm.MAX_SIZE_MBYTES * 1024 * 1024
        size_bytes = len(self.file.data.read())
        self.file.data.seek(0)

        if size_bytes > max_bytes:
            self.file.errors = (f"File size exceeds {LibraryPrepForm.MAX_SIZE_MBYTES} MB",)
            return False
        
        prep_table = pd.read_excel(self.file.data, "prep_table")
        self.file.data.seek(0)
        libraries = dict([(library.id, library.name) for library in self.lab_prep.libraries])

        for i, (idx, row) in enumerate(prep_table.iterrows()):
            
            if pd.notna(row["library_id"]) and pd.isna(row["library_name"]):
                self.file.errors = (f"Library name missing in row {i + 2}",)
                return False
            
            if pd.isna(row["library_id"]) and pd.notna(row["library_name"]):
                self.file.errors = (f"Library ID missing in row {i + 2}",)
                return False
            
            if pd.isna(row["library_id"]) and pd.isna(row["library_name"]):
                continue
            
            if libraries[row["library_id"]] != row["library_name"]:
                self.file.errors = (f"Library ID and name mismatch in row {i + 2}",)
                return False
                    
        return True

    def process_request(self, user: models.User) -> Response:
        if not self.validate():
            return self.make_response()
        
        hash = str(uuid4())
        path = os.path.join(current_app.config["MEDIA_FOLDER"], FileType.LIBRARY_PREP_FILE.dir, f"{hash}.xlsx")
        self.file.data.save(path)
        size_bytes = os.path.getsize(path)

        if self.lab_prep.plate_id is not None:
            plate = db.clear_plate(self.lab_prep.plate_id)
        else:
            plate = db.create_plate(
                name=f"P-{self.lab_prep.name}",
                num_cols=12, num_rows=8,
                owner_id=user.id
            )
            self.lab_prep.plate_id = plate.id

        prep_table = pd.read_excel(path, sheet_name="prep_table")
        for _, row in prep_table.iterrows():
            if pd.isna(row["library_id"]):
                continue

            well_idx = plate.get_well_idx(row["plate_well"].strip())

            db.add_library_to_plate(plate_id=plate.id, library_id=row["library_id"], well_idx=well_idx)

        if self.lab_prep.prep_file is not None:
            size_bytes = os.path.getsize(path)
            self.lab_prep.prep_file.uuid = hash
            self.lab_prep.prep_file.size_bytes = size_bytes
            self.lab_prep.prep_file.timestamp_utc = to_utc(db.timestamp())
        else:
            db_file = db.create_file(
                name=f"{self.lab_prep.name}_prep",
                type=FileType.LIBRARY_PREP_FILE,
                extension=".xlsx",
                uploader_id=user.id,
                size_bytes=size_bytes,
                uuid=hash
            )

            self.lab_prep.prep_file_id = db_file.id

        self.lab_prep = db.update_lab_prep(self.lab_prep)

        flash("Table saved!", "success")
        return make_response(redirect=url_for("lab_preps_page.lab_prep_page", lab_prep_id=self.lab_prep.id))


        
