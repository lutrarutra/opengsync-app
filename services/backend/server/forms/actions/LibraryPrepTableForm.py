import os
from uuid6 import uuid7
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from fastapi import Request, Depends
from fastapi.responses import Response
from sqlalchemy import orm
from loguru import logger

from opengsync_db import models, SyncSession, queries as Q, categories as C

from ...core import exceptions as exc, responses, dependencies, config
from ...components import inputs
from ...components.tables import (
    TextColumn,
    FloatColumn,
    IntegerColumn,
)
from ...components.tables.spreadsheet import (
    InvalidCellValue,
    MissingCellValue,
    DuplicateCellValue,
)
from ..HTMXForm import HTMXForm


class LibraryPrepTableForm(HTMXForm):
    template_path = "workflows/library_prep/upload-prep_table.html"

    spreadsheet = inputs.spreadsheet.SpreadsheetFileField(
        columns=[
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
            TextColumn("kit_i5", "kit_i5", 100),
            TextColumn("name_i5", "name_i5", 100),
            TextColumn("sequence_i5", "sequence_i5", 100),
            FloatColumn("lib_conc_ng_ul", "lib_conc_ng_ul", 100),
        ], sheet_name="prep_table"
    )

    def __init__(
        self,
        request: Request,
        lab_prep: models.LabPrep,
    ) -> None:
        super().__init__(request)
        self.lab_prep = lab_prep
        self._context["lab_prep"] = lab_prep
        self._validated_df: pd.DataFrame | None = None

        rows = []
        for library in lab_prep.libraries:
            row = {
                "library_id": library.id,
                "library_name": library.name,
                "requestor": library.seq_request.requestor.name if library.seq_request else "",
                "pool": "",
                "plate": "",
                "plate_well": "",
                "index_well": "",
                "kit_i7": "",
                "name_i7": library.indices[0].name_i7 if library.indices else "",
                "sequence_i7": library.sequences_i7_str(";") if library.indices else "",
                "kit_i5": "",
                "name_i5": library.indices[0].name_i5 if library.indices else "",
                "sequence_i5": library.sequences_i5_str(";") if library.indices else "",
                "lib_conc_ng_ul": library.qubit_concentration if library.qubit_concentration else "",
            }
            rows.append(row)

        columns = [col.label for col in self.spreadsheet.columns.values()]
        df = pd.DataFrame(rows, columns=columns) if rows else pd.DataFrame(columns=columns)

        self.spreadsheet.configure(
            df=df,
            csrf_token=self.csrf_token_value,
            editable=True,
            allow_new_rows=True,
            can_be_empty=True,
        )

    @staticmethod
    def upload(
        lab_prep_id: int,
        request: Request,
        current_user: models.User = Depends(dependencies.require_insider),
        session: SyncSession = Depends(dependencies.db_session),
    ):
        lab_prep = session.get_one(
            Q.lab_prep.select(id=lab_prep_id),
            options=[
                orm.selectinload(models.LabPrep.libraries).selectinload(models.Library.indices),
                orm.selectinload(models.LabPrep.plates),
                orm.selectinload(models.LabPrep.prep_file).selectinload(models.MediaFile.uploader),
                orm.selectinload(models.LabPrep.libraries).selectinload(models.Library.seq_request).selectinload(models.SeqRequest.requestor),
            ],
        )
        form = LibraryPrepTableForm(request, lab_prep=lab_prep)
        form.validate()
        df = form.spreadsheet.data

        cols = [col.label for col in form.spreadsheet.columns.values()]
        for col in cols:
            if col not in df.columns:
                df[col] = None

        prep_table = df.dropna(subset=["library_id", "library_name"], how="all")
        libraries = {library.id: library.name for library in form.lab_prep.libraries}

        duplicate_plate_well = prep_table.duplicated(subset=["plate_well", "plate"], keep=False)

        for idx, row in prep_table.iterrows():
            pool_val = row.get("pool")
            pool_val = str(pool_val).strip().lower() if pd.notna(pool_val) else ""
            if pool_val == "t":
                continue

            if pd.notna(row.get("library_id")) and pd.isna(row.get("library_name")):
                form.spreadsheet.add_error(idx, "library_name", MissingCellValue("Library Name is required when Library ID is provided"))

            if duplicate_plate_well.at[idx]:
                form.spreadsheet.add_error(
                    idx, ["plate_well", "plate"],
                    DuplicateCellValue(f"Plate Well '{row['plate_well']}' is duplicated.")
                )

            if pd.isna(row.get("library_id")):
                continue

            try:
                library_id = int(row["library_id"])
            except ValueError:
                logger.error(f"Invalid library_id '{row['library_id']}' at row {idx}.")
                form.spreadsheet.add_error(idx, "library_id", InvalidCellValue(f"Invalid library_id '{row['library_id']}'"))
                continue

            if library_id not in libraries:
                form.spreadsheet.add_error(idx, "library_id", InvalidCellValue(f"Library ID '{library_id}' is not part of this prep."))
            elif libraries[library_id] != row["library_name"]:
                form.spreadsheet.add_error(
                    idx, ["library_name", "library_id"],
                    InvalidCellValue(f"Library Name '{row['library_name']}' does not match the existing library name '{libraries[library_id]}'")
                )

        if form.errors:
            raise exc.FormValidationException(form)

        hash = uuid7().__str__()
        media_folder = config.settings.app_config.media_folder
        file_dir = C.MediaFileType.LIBRARY_PREP_FILE.dir
        ext = form.spreadsheet.file_extension or "xlsx"
        filepath = os.path.join(media_folder, file_dir, f"{hash}.{ext}")

        os.makedirs(os.path.join(media_folder, file_dir), exist_ok=True)

        with open(filepath, "wb") as f:
            f.write(form.spreadsheet.file_bytes)
        size_bytes = len(form.spreadsheet.file_bytes)

        form.lab_prep.plates.clear()

        for plate_name, _df in df.groupby("plate", dropna=False):
            if pd.isna(plate_name) or not str(plate_name).strip():
                plate = session.save(
                    Q.plate.create(
                        name=f"P-{form.lab_prep.name}",
                        num_cols=12, num_rows=8,
                        owner=current_user,
                    ),
                    flush=True,
                )
            else:
                plate = session.save(
                    Q.plate.create(
                        name=f"P-{form.lab_prep.name}-{plate_name}",
                        num_cols=12, num_rows=8,
                        owner=current_user,
                    ),
                    flush=True,
                )

            for _, row in _df.iterrows():
                library_id = row.get("library_id")
                if pd.isna(library_id):
                    continue

                library = session.get_one(Q.library.select(id=int(library_id)))

                # Mark as failed if pool == "x"
                pool_val = row.get("pool")
                pool_val = str(pool_val).strip().lower() if pd.notna(pool_val) else ""
                if pool_val == "x":
                    library.status_id = C.LibraryStatus.FAILED.id
                    session.save(library)

                # Update qubit concentration
                lib_conc = row.get("lib_conc_ng_ul")
                if pd.notna(lib_conc):
                    library.qubit_concentration = float(lib_conc)
                    session.save(library)

                # Add library to plate well
                plate_well = row.get("plate_well")
                if pd.notna(plate_well) and (plate_well := str(plate_well).strip()):
                    well_idx = plate.get_well_idx(plate_well)
                    plate.sample_links.append(
                        models.links.SamplePlateLink(
                            plate_id=plate.id,
                            well_idx=well_idx,
                            library_id=int(library_id),
                        )
                    )

            form.lab_prep.plates.append(plate)

        if (prep_file := form.lab_prep.prep_file) is not None:
            prep_file.uuid = hash
            prep_file.size_bytes = size_bytes
            prep_file.timestamp_utc = datetime.now(timezone.utc)
            session.save(prep_file)
        else:
            new_file = Q.media_file.create(
                name=f"{form.lab_prep.name}_prep",
                type=C.MediaFileType.LIBRARY_PREP_FILE,
                extension=f".{ext}",
                uploader_id=current_user.id,
                size_bytes=size_bytes,
                uuid=hash,
                lab_prep_id=form.lab_prep.id,
            )
            session.save(new_file)

        session.save(form.lab_prep)

        return responses.htmx_response(
            redirect=responses.url_for("lab_prep_page", lab_prep_id=form.lab_prep.id),
            flash=responses.flash("Table saved!", "success"),
        )
    
    @staticmethod
    def render(
        lab_prep_id: int,
        request: Request,
        session: SyncSession = Depends(dependencies.db_session),
    ):
        lab_prep = session.get_one(
            Q.lab_prep.select(id=lab_prep_id),
            options=[
                orm.selectinload(models.LabPrep.libraries).selectinload(models.Library.indices),
                orm.selectinload(models.LabPrep.prep_file).selectinload(models.MediaFile.uploader),
                orm.selectinload(models.LabPrep.libraries).selectinload(models.Library.seq_request).selectinload(models.SeqRequest.requestor),
            ],
        )
        form = LibraryPrepTableForm(request, lab_prep=lab_prep)
        return form.make_response()