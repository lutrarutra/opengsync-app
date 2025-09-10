import os
from uuid_extensions import uuid7str

import numpy as np
import pandas as pd

from flask import Response, url_for, flash
from flask_htmx import make_response

from opengsync_db import models, to_utc
from opengsync_db.categories import MediaFileType, LibraryStatus

from .... import logger, db  # noqa F401
from ....core import exceptions
from ....core.RunTime import runtime
from ...HTMXFlaskForm import HTMXFlaskForm
from ....forms.SpreadsheetFile import SpreadsheetFile
from ....tools.spread_sheet_components import InvalidCellValue, MissingCellValue, DuplicateCellValue, TextColumn, FloatColumn, IntegerColumn


class LibraryPrepForm(HTMXFlaskForm):
    _template_path = "workflows/library_prep/prep_table.html"

    columns = [
        IntegerColumn("library_id", "library_id", 100, read_only=True),
        TextColumn("library_name", "library_name", 250, read_only=True),
        TextColumn("requestor", "requestor", 200, read_only=True),
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

            if pd.isna(row["library_id"]):
                continue

            try:
                library_id = int(row["library_id"])
            except ValueError:
                logger.error(f"Invalid library_id '{row['library_id']}' at row {idx}.")
                raise exceptions.InternalServerErrorException(f"Invalid library_id '{row['library_id']}' at row {idx}.")

            if library_id not in libraries:
                self.table.add_error(idx, "library_id", InvalidCellValue(f"Library ID '{library_id}' is not part of this prep."))
            elif libraries[library_id] != row["library_name"]:
                self.table.add_error(idx, ["library_name", "library_id"], InvalidCellValue(f"Library Name '{row['library_name']}' does not match the existing library name '{libraries[int(row['library_id'])]}'.. Did you move the rows?"))

        if self.table.errors:
            self.table._data = prep_table[[label for label in self.table.cell_errors.keys()]].replace(np.nan, "").values.tolist()
            return False
        
        self.df = prep_table
        return True

    def process_request(self, user: models.User) -> Response:
        if not self.validate():
            return self.make_response()
        
        hash = uuid7str()
        path = os.path.join(runtime.app.media_folder, MediaFileType.LIBRARY_PREP_FILE.dir, f"{hash}.xlsx")
        self.table.file.data.save(path)
        size_bytes = os.path.getsize(path)

        for plate in self.lab_prep.plates:
            db.plates.delete(plate.id)

        db.refresh(self.lab_prep)

        for plate, _df in self.df.groupby("plate", dropna=False):
            if pd.isna(plate):
                plate = db.plates.create(
                    name=f"P-{self.lab_prep.name}",
                    num_cols=12, num_rows=8,
                    owner_id=user.id
                )
            else:
                try:
                    plate = int(plate)  # type: ignore
                except ValueError:
                    pass
                
                plate = db.plates.create(
                    name=f"P-{self.lab_prep.name}-{plate}",
                    num_cols=12, num_rows=8,
                    owner_id=user.id
                )

            for _, row in _df.iterrows():
                if pd.isna(library_id := row["library_id"]):
                    continue

                library_id = int(library_id)
                if (library := db.libraries.get(library_id)) is None:
                    logger.error(f"Library {library_id} not found")
                    raise ValueError(f"Library {library_id} not found")
                
                db.refresh(library)
                
                if pd.notna(row["pool"]) and str(row["pool"]).strip().lower() == "x":
                    library.status = LibraryStatus.FAILED
                    db.libraries.update(library)
                
                if pd.notna(row["lib_conc_ng_ul"]):
                    if (library := db.libraries.get(library_id)) is None:
                        logger.error(f"Library {library_id} not found")
                        raise ValueError(f"Library {library_id} not found")
                    
                    library.qubit_concentration = float(row["lib_conc_ng_ul"])
                    db.libraries.update(library)
                    db.flush()

                well_idx = plate.get_well_idx(row["plate_well"].strip())
                plate = db.plates.add_library(plate_id=plate.id, library_id=library_id, well_idx=well_idx)
            
            self.lab_prep.plates.append(plate)
        
        db.lab_preps.update(self.lab_prep)

        if (file := self.lab_prep.prep_file) is not None:
            size_bytes = os.path.getsize(path)
            file.uuid = hash
            file.size_bytes = size_bytes
            file.timestamp_utc = to_utc(db.timestamp())
            db.media_files.update(file)
        else:
            db.media_files.create(
                name=f"{self.lab_prep.name}_prep",
                type=MediaFileType.LIBRARY_PREP_FILE,
                extension=".xlsx",
                uploader_id=user.id,
                size_bytes=size_bytes,
                uuid=hash,
                lab_prep_id=self.lab_prep.id
            )

        db.lab_preps.update(self.lab_prep)

        flash("Table saved!", "success")
        return make_response(redirect=url_for("lab_preps_page.lab_prep", lab_prep_id=self.lab_prep.id))


        
