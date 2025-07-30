import os
from uuid import uuid4

import numpy as np
import pandas as pd

from flask import Response, current_app, url_for, flash
from flask_htmx import make_response

from opengsync_db import models, to_utc
from opengsync_db.categories import FileType, LibraryStatus

from .... import logger, db  # noqa F401
from ...HTMXFlaskForm import HTMXFlaskForm
from ....forms.SpreadsheetFile import SpreadsheetFile
from ....tools.spread_sheet_components import InvalidCellValue, MissingCellValue, DuplicateCellValue, TextColumn, FloatColumn, IntegerColumn


class LibraryPrepForm(HTMXFlaskForm):
    _template_path = "workflows/library_prep/prep_table.html"

    columns = [
        IntegerColumn("library_id", "library_id", 100),
        TextColumn("library_name", "library_name", 250),
        TextColumn("requestor", "requestor", 200),
        TextColumn("pool", "pool", 200),
        TextColumn("plate", "plate", 100, optional_col=True),
        TextColumn("plate_well", "plate_well", 150, clean_up_fnc=lambda x: x.strip().upper()),
        TextColumn("index_well", "index_well", 150),
        TextColumn("kit_i7", "kit_i7", 100),
        TextColumn("name_i7", "name_i7", 100),
        TextColumn("sequence_i7", "sequence_i7", 100),
        TextColumn("kit_i5", "kit_i5", 100,),
        TextColumn("name_i5", "name_i5", 100),
        TextColumn("sequence_i5", "sequence_i5", 100),
        FloatColumn("lib_conc_ng_ul", "lib_conc_ng_ul", 100),
    ]

    def __init__(self, lab_prep: models.LabPrep, formdata: dict | None = None):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self.lab_prep = lab_prep
        self._context["lab_prep"] = lab_prep

        if (csrf_token := formdata.get("csrf_token") if formdata is not None else None) is None:
            csrf_token = self.csrf_token._value()  # type: ignore

        self.table: SpreadsheetFile = SpreadsheetFile(
            columns=LibraryPrepForm.columns,
            post_url=url_for("lab_preps_htmx.prep_table_upload_form", lab_prep_id=lab_prep.id),
            csrf_token=csrf_token,
            sheet_name="prep_table",
            formdata=formdata,
        )
        self.table.cell_errors["library_name"] = []  # this makes sure that library_name col is always showed for errors
    
    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if not self.table.validate():
            return False
        
        prep_table = self.table.df
        
        cols = [col.label for col in self.columns]
        for col in cols:
            if col not in prep_table.columns:
                prep_table[col] = None

        prep_table = prep_table.dropna(subset=["library_id", "library_name"], how="all")
        libraries = dict([(library.id, library.name) for library in self.lab_prep.libraries])

        duplicate_plate_well = prep_table.duplicated(subset=["plate_well", "plate"], keep=False)

        for idx, row in prep_table.iterrows():
            if str(row["pool"]).strip().lower() == "t":
                continue
            
            if pd.notna(row["library_id"]) and pd.isna(row["library_name"]):
                self.table.add_error(idx, "library_name", MissingCellValue("Library Name is required when Library ID is provided"))
            
            if duplicate_plate_well.at[idx]:
                self.table.add_error(idx, ["plate_well", "plate"], DuplicateCellValue(f"Plate Well '{row['plate_well']}' is duplicated."))

            if int(row["library_id"]) not in libraries:
                self.table.add_error(idx, "library_id", InvalidCellValue(f"Library ID '{row['library_id']}' is not part of this prep."))
            elif pd.notna(row["library_id"]) and libraries[int(row["library_id"])] != row["library_name"]:
                self.table.add_error(idx, ["library_name", "library_id"], InvalidCellValue(f"Library Name '{row['library_name']}' does not match the existing library name '{libraries[int(row['library_id'])]}'.. Did you move the rows?"))

        if self.table.errors:
            self.table._data = prep_table[[label for label in self.table.cell_errors.keys()]].replace(np.nan, "").values.tolist()
            return False
        
        self.df = prep_table
        return True

    def process_request(self, user: models.User) -> Response:
        if not self.validate():
            return self.make_response()
        
        hash = str(uuid4())
        path = os.path.join(current_app.config["MEDIA_FOLDER"], FileType.LIBRARY_PREP_FILE.dir, f"{hash}.xlsx")
        self.table.file.data.save(path)
        size_bytes = os.path.getsize(path)

        for plate in self.lab_prep.plates:
            db.delete_plate(plate.id)

        for plate, _df in self.df.groupby("plate", dropna=False):
            if pd.isna(plate):
                plate = db.create_plate(
                    name=f"P-{self.lab_prep.name}",
                    num_cols=12, num_rows=8,
                    owner_id=user.id
                )
            else:
                try:
                    plate = int(plate)  # type: ignore
                except ValueError:
                    pass
                
                plate = db.create_plate(
                    name=f"P-{self.lab_prep.name}-{plate}",
                    num_cols=12, num_rows=8,
                    owner_id=user.id
                )

            for _, row in _df.iterrows():
                if pd.isna(library_id := row["library_id"]):
                    continue

                library_id = int(library_id)
                if (library := db.get_library(library_id)) is None:
                    logger.error(f"Library {library_id} not found")
                    raise ValueError(f"Library {library_id} not found")
                
                db.refresh(library)
                
                if pd.notna(row["pool"]) and str(row["pool"]).strip().lower() == "x":
                    library.status = LibraryStatus.FAILED
                    library = db.update_library(library)
                    continue
                
                if pd.notna(row["lib_conc_ng_ul"]):
                    if (library := db.get_library(library_id)) is None:
                        logger.error(f"Library {library_id} not found")
                        raise ValueError(f"Library {library_id} not found")
                    
                    library.qubit_concentration = float(row["lib_conc_ng_ul"])
                    library = db.update_library(library)
                    db.flush()

                well_idx = plate.get_well_idx(row["plate_well"].strip())
                plate = db.add_library_to_plate(plate_id=plate.id, library_id=library_id, well_idx=well_idx)
            
            self.lab_prep.plates.append(plate)
        
        self.lab_prep = db.update_lab_prep(self.lab_prep)

        if self.lab_prep.prep_file is not None:
            size_bytes = os.path.getsize(path)
            self.lab_prep.prep_file.uuid = hash
            self.lab_prep.prep_file.size_bytes = size_bytes
            self.lab_prep.prep_file.timestamp_utc = to_utc(db.timestamp())
        else:
            db.create_file(
                name=f"{self.lab_prep.name}_prep",
                type=FileType.LIBRARY_PREP_FILE,
                extension=".xlsx",
                uploader_id=user.id,
                size_bytes=size_bytes,
                uuid=hash,
                lab_prep_id=self.lab_prep.id
            )

        self.lab_prep = db.update_lab_prep(self.lab_prep)

        flash("Table saved!", "success")
        return make_response(redirect=url_for("lab_preps_page.lab_prep", lab_prep_id=self.lab_prep.id))


        
