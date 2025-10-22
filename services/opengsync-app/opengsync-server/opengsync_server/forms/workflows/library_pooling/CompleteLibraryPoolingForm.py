import os

import pandas as pd
import openpyxl
from openpyxl.utils import get_column_letter

from flask import Response, url_for, flash
from flask_htmx import make_response

from opengsync_db import models
from opengsync_db.categories import PoolType, SeqRequestStatus, LibraryStatus, LibraryType, IndexType, BarcodeOrientation

from .... import logger, db, tools
from ....core.RunTime import runtime
from ....core import exceptions
from ...MultiStepForm import MultiStepForm


class CompleteLibraryPoolingForm(MultiStepForm):
    _template_path = "workflows/library_pooling/complete-pooling.html"
    _workflow_name = "library_pooling"
    _step_name = "complete_library_pooling"

    def __init__(self, lab_prep: models.LabPrep, uuid: str | None, formdata: dict | None = None):
        MultiStepForm.__init__(
            self, workflow=CompleteLibraryPoolingForm._workflow_name,
            step_name=CompleteLibraryPoolingForm._step_name, uuid=uuid,
            formdata=formdata, step_args={"lab_prep": lab_prep},
        )
        self.lab_prep = lab_prep
        self._context["lab_prep"] = lab_prep
        self.barcode_table = self.tables["barcode_table"]

    def prepare(self):
        self.barcode_table["orientation_id"] = self.barcode_table["orientation_i7_id"]
        self.barcode_table.loc[
            pd.notna(self.barcode_table["orientation_i7_id"]) &
            (self.barcode_table["orientation_i7_id"] != self.barcode_table["orientation_i5_id"]),
            "orientation_id"
        ] = None
        self.barcode_table = tools.check_indices(self.barcode_table, groupby="pool")
        self._context["df"] = self.barcode_table
        self._context["groupby"] = "pool"

    def validate(self) -> bool:
        validated = super().validate()
        return validated

    def process_request(self, user: models.User) -> Response:
        if not self.validate():
            return self.make_response()
        
        barcode_table = self.tables["barcode_table"]
        
        lab_prep_libraries = db.pd.get_lab_prep_libraries(self.lab_prep.id)
        barcode_table["old_pool_id"] = lab_prep_libraries.set_index("library_id").loc[barcode_table["library_id"], "pool_id"].values
        barcode_table["experiment_id"] = None

        for pool in self.lab_prep.pools:
            barcode_table.loc[barcode_table["old_pool_id"] == pool.id, "experiment_id"] = pool.experiment_id
            db.pools.delete(pool.id)

        barcode_table["selected"] = ~barcode_table["pool"].astype(str).str.strip().str.lower().isin(["x", "t"])
        selected_libraries = barcode_table[barcode_table["selected"]].copy()

        if len(selected_libraries["pool"].unique()) == 1:
            selected_libraries["pool"] = "1"
            barcode_table.loc[barcode_table["selected"], "pool"] = "1"
        
        # if all the experiment_ids are the same in the pool we can link it with the experiment
        experiment_mappings = {}
        for pool_suffix, _df in selected_libraries.groupby("pool"):
            if len(_df["experiment_id"].unique()) == 1 and pd.notna(_df["experiment_id"].iloc[0]):
                experiment_mappings[pool_suffix] = _df["experiment_id"].iloc[0]
                    
        pools = {}
        if len(selected_libraries["pool"].unique()) > 1:
            for pool_suffix, _df in selected_libraries.groupby("pool"):
                pools[pool_suffix] = db.pools.create(
                    name=f"{self.lab_prep.name}_{pool_suffix}", pool_type=PoolType.INTERNAL,
                    contact_email=user.email, contact_name=user.name, owner_id=user.id,
                    lab_prep_id=self.lab_prep.id, experiment_id=experiment_mappings.get(pool_suffix, None),
                )
        elif len(selected_libraries) > 0:
            pools["1"] = db.pools.create(
                name=self.lab_prep.name, pool_type=PoolType.INTERNAL,
                contact_email=user.email, contact_name=user.name, owner_id=user.id,
                lab_prep_id=self.lab_prep.id, experiment_id=experiment_mappings.get("1", None)
            )

        request_ids = set()

        if len(barcode_table.drop_duplicates(["library_id", "index_type_id"])) != len(barcode_table.drop_duplicates(["library_id"])):
            logger.error(f"{self.uuid}: some have more than one unique index_type_id entries in barcode table.")
            raise exceptions.InternalServerErrorException(f"{self.uuid}: some have more than one unique index_type_id entries in barcode table.")

        for (library_id, pool, index_type_id), df in barcode_table.groupby(["library_id", "pool", "index_type_id"], dropna=False):
            if str(pool).strip().lower() == "t":
                continue
            
            if (library := db.libraries.get(library_id)) is None:
                logger.error(f"{self.uuid}: Library {library_id} not found")
                raise ValueError(f"{self.uuid}: Library {library_id} not found")

            if pool == "x":
                if df["sequence_i7"].isna().all():
                    index_type = None
                else:
                    if library.type == LibraryType.TENX_SC_ATAC:
                        if len(df) != 4:
                            logger.warning(f"{self.uuid}: Expected 4 barcodes (i7) for index type {library.index_type}, found {len(df)}.")
                        index_type = IndexType.TENX_ATAC_INDEX
                    else:
                        if len(df) != 1:
                            logger.warning(f"{self.uuid}: Expected 1 barcode for index type {library.index_type}, found {len(df)}.")
                        if df["sequence_i5"].isna().all():
                            index_type = IndexType.SINGLE_INDEX_I7
                        else:
                            index_type = IndexType.DUAL_INDEX
            else:
                try:
                    index_type_id = int(index_type_id)
                    index_type = IndexType.get(index_type_id)
                except ValueError:
                    logger.error(f"{self.uuid}: Invalid index_type_id {index_type_id} for library {library_id}")
                    raise exceptions.InternalServerErrorException(f"{self.uuid}: Invalid index_type_id {index_type_id} for library {library_id}")
            
            library = db.libraries.remove_indices(library_id=library.id)
            request_ids.add(library.seq_request_id)
            library.index_type = index_type
            library.pool_id = None
            library.status = LibraryStatus.POOLED if str(pool).strip().lower() != "x" else LibraryStatus.FAILED
            library.pool_id = None
            db.libraries.update(library)
            
            if str(pool).strip().lower() != "x":
                library = db.libraries.add_to_pool(library_id=library.id, pool_id=pools[pool].id)

            if index_type == IndexType.TENX_ATAC_INDEX:
                if len(df) != 4:
                    logger.warning(f"{self.uuid}: Expected 4 barcodes (i7) for index type {library.index_type}, found {len(df)}.")
            else:
                if len(df) != 1:
                    logger.warning(f"{self.uuid}: Expected 1 barcode for index type {library.index_type}, found {len(df)}.")

            for _, row in df.iterrows():
                if pool == "x" and pd.isna(row["sequence_i7"]):
                    continue
                
                orientation = None
                if pd.notna(row["orientation_i7_id"]):
                    orientation = BarcodeOrientation.get(row["orientation_i7_id"])

                if orientation is not None and pd.notna(row["orientation_i5_id"]):
                    if orientation.id != row["orientation_i5_id"]:
                        logger.error(f"{self.uuid}: Conflicting orientations for i7 and i5 in library {row['library_name']}.")
                        raise ValueError("Conflicting orientations for i7 and i5.")
                
                library = db.libraries.add_index(
                    library_id=library.id,
                    index_kit_i7_id=int(row["kit_i7_id"]) if pd.notna(row["kit_i7_id"]) else None,
                    index_kit_i5_id=int(row["kit_i5_id"]) if pd.notna(row["kit_i5_id"]) else None,
                    name_i7=row["name_i7"] if pd.notna(row["name_i7"]) else None,
                    name_i5=row["name_i5"] if pd.notna(row["name_i5"]) else None,
                    sequence_i7=row["sequence_i7"],
                    sequence_i5=row["sequence_i5"] if pd.notna(row["sequence_i5"]) else None,
                    orientation=orientation,
                )
        
        if self.lab_prep.prep_file is not None:
            path = os.path.join(runtime.app.media_folder, self.lab_prep.prep_file.path)
            wb = openpyxl.load_workbook(path)
            active_sheet = wb["prep_table"]
            
            column_mapping: dict[str, str] = {}
            for col_i in range(1, min(active_sheet.max_column, 96)):
                col = get_column_letter(col_i + 1)
                column_name = active_sheet[f"{col}1"].value
                column_mapping[column_name] = col
            
            for i, ((library_id, pool, index_type_id, index_well), df) in enumerate(barcode_table.groupby(["library_id", "pool", "index_type_id", "index_well"], dropna=False)):
                if (library := db.libraries.get(int(library_id))) is None:
                    logger.error(f"{self.uuid}: Library {library_id} not found")
                    raise ValueError(f"{self.uuid}: Library {library_id} not found")

                active_sheet[f"{column_mapping['sequence_i7']}{i + 2}"].value = library.sequences_i7_str(sep=";")
                active_sheet[f"{column_mapping['sequence_i5']}{i + 2}"].value = library.sequences_i5_str(sep=";")
                active_sheet[f"{column_mapping['name_i7']}{i + 2}"].value = ";".join([index.name_i7 for index in library.indices if index.name_i7])
                active_sheet[f"{column_mapping['name_i5']}{i + 2}"].value = ";".join([index.name_i5 for index in library.indices if index.name_i5])
                active_sheet[f"{column_mapping['pool']}{i + 2}"].value = pool
                active_sheet[f"{column_mapping['kit_i7']}{i + 2}"].value = ";".join([str(s) for s in df["kit_i7"] if pd.notna(s)])
                active_sheet[f"{column_mapping['kit_i5']}{i + 2}"].value = ";".join([str(s) for s in df["kit_i5"] if pd.notna(s)])
                active_sheet[f"{column_mapping['index_well']}{i + 2}"].value = index_well

            logger.debug(f"Overwriting existing file: {os.path.join(runtime.app.media_folder, self.lab_prep.prep_file.path)}")
            wb.save(path)

        for request_id in request_ids:
            if (seq_request := db.seq_requests.get(request_id)) is None:
                logger.error(f"{self.uuid}: SeqRequest {request_id} not found")
                raise ValueError(f"{self.uuid}: SeqRequest {request_id} not found")
            
            prepared = True
            for library in seq_request.libraries:
                prepared = prepared and library.status.id >= LibraryStatus.POOLED.id

            if prepared and seq_request.status == SeqRequestStatus.ACCEPTED:
                seq_request.status = SeqRequestStatus.PREPARED
                db.seq_requests.update(seq_request)

        self.complete()
        flash("Library Indexing completed!", "success")
        return make_response(redirect=url_for("lab_preps_page.lab_prep", lab_prep_id=self.lab_prep.id))
