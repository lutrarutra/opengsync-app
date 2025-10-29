import os

import pandas as pd
import openpyxl
from openpyxl.utils import get_column_letter

from flask import Response, url_for, flash
from flask_htmx import make_response

from opengsync_db import models
from opengsync_db.categories import PoolType, SeqRequestStatus, LibraryStatus, LibraryType, IndexType, BarcodeOrientation

from .... import logger, db, tools
from ....tools import utils
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
        if (tenx_atac_barcode_table := self.tables.get("tenx_atac_barcode_table")) is not None:
            self.barcode_table = pd.concat([self.barcode_table, tenx_atac_barcode_table], ignore_index=True)

    def prepare(self):
        self.barcode_table["orientation_id"] = self.barcode_table["orientation_i7_id"]
        self.barcode_table.loc[
            pd.notna(self.barcode_table["orientation_i7_id"]) &
            (self.barcode_table["orientation_i7_id"] != self.barcode_table["orientation_i5_id"]),
            "orientation_id"
        ] = None
        self.barcode_table = tools.check_indices(self.barcode_table, groupby="pool")
        self._context["groupby"] = "pool"
        self._context["df"] = self.barcode_table

    def validate(self) -> bool:
        validated = super().validate()
        return validated

    def process_request(self, user: models.User) -> Response:
        if not self.validate():
            self.prepare()
            return self.make_response()
        
        lab_prep_libraries = db.pd.get_lab_prep_libraries(self.lab_prep.id)

        pool_data = {
            "name": [],
            "library_id": [],
            "index_type_id": [],
        }
        barcode_table = self.tables["barcode_table"]
        for _, row in barcode_table.iterrows():
            pool_name = row["pool"]
            if str(pool_name).strip().lower() in ["x", "t"]:
                continue

            pool_data["name"].append(pool_name)
            pool_data["library_id"].append(row["library_id"])
            pool_data["index_type_id"].append(row["index_type_id"])

        if (tenx_atac_barcode_table := self.tables.get("tenx_atac_barcode_table")) is not None:
            for _, row in tenx_atac_barcode_table.iterrows():
                pool_name = row["pool"]
                if str(pool_name).strip().lower() in ["x", "t"]:
                    continue

                pool_data["name"].append(pool_name)
                pool_data["library_id"].append(row["library_id"])
                pool_data["index_type_id"].append(row["index_type_id"])

        library_pooling_table = pd.DataFrame(pool_data)
        library_pooling_table["old_pool_id"] = utils.map_columns(library_pooling_table, lab_prep_libraries, idx_columns="library_id", col="pool_id")
        library_pooling_table["experiment_id"] = None

        for pool in self.lab_prep.pools:
            library_pooling_table.loc[library_pooling_table["old_pool_id"] == pool.id, "experiment_id"] = pool.experiment_id
            db.pools.delete(pool.id)

        if len(library_pooling_table["name"].unique()) == 1:
            library_pooling_table["name"] = "1"
        
        # if all the experiment_ids are the same in the pool we can link it with the experiment
        experiment_mappings = {}
        for pool_suffix, _df in library_pooling_table.groupby("name"):
            if len(_df["experiment_id"].unique()) == 1 and pd.notna(_df["experiment_id"].iloc[0]):
                experiment_mappings[pool_suffix] = _df["experiment_id"].iloc[0]
                    
        pools = {}
        if len(library_pooling_table["name"].unique()) > 1:
            for pool_suffix, _ in library_pooling_table.groupby("name"):
                pools[pool_suffix] = db.pools.create(
                    name=f"{self.lab_prep.name}_{pool_suffix}", pool_type=PoolType.INTERNAL,
                    contact_email=user.email, contact_name=user.name, owner_id=user.id,
                    lab_prep_id=self.lab_prep.id, experiment_id=experiment_mappings.get(pool_suffix, None),
                )
        elif len(library_pooling_table["name"].unique()) > 0:
            pools["1"] = db.pools.create(
                name=self.lab_prep.name, pool_type=PoolType.INTERNAL,
                contact_email=user.email, contact_name=user.name, owner_id=user.id,
                lab_prep_id=self.lab_prep.id, experiment_id=experiment_mappings.get("1", None)
            )

        request_ids = set()

        if len(library_pooling_table.drop_duplicates(["library_id", "index_type_id"])) != len(library_pooling_table.drop_duplicates(["library_id"])):
            logger.error(f"{self.uuid}: some have more than one unique index_type_id entries in barcode table.")
            raise exceptions.InternalServerErrorException(f"{self.uuid}: some have more than one unique index_type_id entries in barcode table.")

        for (library_id, pool, index_type_id), _ in library_pooling_table.groupby(["library_id", "name", "index_type_id"], dropna=False):
            library = db.libraries[int(library_id)]

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

            match index_type:
                case IndexType.TENX_ATAC_INDEX:
                    if tenx_atac_barcode_table is None:
                        logger.error(f"{self.uuid}: TENX_ATAC_INDEX selected but no tenx_atac_barcode_table found.")
                        raise exceptions.InternalServerErrorException(f"{self.uuid}: TENX_ATAC_INDEX selected but no tenx_atac_barcode_table found.")
                    
                    df = tenx_atac_barcode_table[tenx_atac_barcode_table["library_id"] == library.id]
                    if index_type == IndexType.TENX_ATAC_INDEX:
                        if len(df) != 4:
                            logger.warning(f"{self.uuid}: Expected 4 barcodes (i7) for index type {library.index_type}, found {len(df)}.")
                case _:
                    df = barcode_table[barcode_table["library_id"] == library.id]
                    if len(df) != 1:
                        logger.warning(f"{self.uuid}: Expected 1 barcode for index type {library.index_type}, found {len(df)}.")

            for _, row in df.iterrows():
                if index_type == IndexType.TENX_ATAC_INDEX:
                    for i in range(1, 5):
                        if pd.isna(row[f"sequence_{i}"]):
                            logger.error(f"{self.uuid}: Missing sequence_{i} for TENX_ATAC_INDEX in library {row['library_name']}.")
                            raise ValueError(f"Missing sequence_{i} for TENX_ATAC_INDEX in library {row['library_name']}.")
                        
                        library = db.libraries.add_index(
                            library_id=library.id,
                            index_kit_i7_id=int(row["kit_id"]) if pd.notna(row["kit_id"]) else None,
                            index_kit_i5_id=None,
                            name_i7=row["name"] or None,
                            name_i5=None,
                            sequence_i7=row[f"sequence_{i}"],
                            sequence_i5=None,
                            orientation=BarcodeOrientation.FORWARD if pd.notna(row["kit_id"]) else None,
                        )
                else:
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

            for i, ((library_id, pool, index_type_id), _) in enumerate(library_pooling_table.groupby(["library_id", "name", "index_type_id"], dropna=False)):
                if (library := db.libraries.get(int(library_id))) is None:
                    logger.error(f"{self.uuid}: Library {library_id} not found")
                    raise ValueError(f"{self.uuid}: Library {library_id} not found")
                
                try:
                    index_type_id = int(index_type_id)
                    index_type = IndexType.get(index_type_id)
                except ValueError:
                    logger.error(f"{self.uuid}: Invalid index_type_id {index_type_id} for library {library_id}")
                    raise exceptions.InternalServerErrorException(f"{self.uuid}: Invalid index_type_id {index_type_id} for library {library_id}")

                if index_type == IndexType.TENX_ATAC_INDEX:
                    if tenx_atac_barcode_table is None:
                        logger.error(f"{self.uuid}: TENX_ATAC_INDEX selected but no tenx_atac_barcode_table found.")
                        raise exceptions.InternalServerErrorException(f"{self.uuid}: TENX_ATAC_INDEX selected but no tenx_atac_barcode_table found.")
                    
                    active_sheet[f"{column_mapping['sequence_i7']}{i + 2}"].value = library.sequences_i7_str(sep=";")
                    active_sheet[f"{column_mapping['sequence_i5']}{i + 2}"].value = None
                    active_sheet[f"{column_mapping['name_i7']}{i + 2}"].value = ";".join(set([index.name_i7 for index in library.indices if index.name_i7]))
                    active_sheet[f"{column_mapping['name_i5']}{i + 2}"].value = None
                    active_sheet[f"{column_mapping['pool']}{i + 2}"].value = pool
                    active_sheet[f"{column_mapping['kit_i7']}{i + 2}"].value = ";".join(set([index.index_kit_i7.identifier for index in library.indices if index.index_kit_i7]))
                    active_sheet[f"{column_mapping['kit_i5']}{i + 2}"].value = None
                    active_sheet[f"{column_mapping['index_well']}{i + 2}"].value = next(iter(barcode_table[barcode_table["library_id"] == library.id]["index_well"].tolist()), None)
                else:

                    active_sheet[f"{column_mapping['sequence_i7']}{i + 2}"].value = library.sequences_i7_str(sep=";")
                    active_sheet[f"{column_mapping['sequence_i5']}{i + 2}"].value = library.sequences_i5_str(sep=";")
                    active_sheet[f"{column_mapping['name_i7']}{i + 2}"].value = ";".join([index.name_i7 for index in library.indices if index.name_i7])
                    active_sheet[f"{column_mapping['name_i5']}{i + 2}"].value = ";".join([index.name_i5 for index in library.indices if index.name_i5])
                    active_sheet[f"{column_mapping['pool']}{i + 2}"].value = pool
                    active_sheet[f"{column_mapping['kit_i7']}{i + 2}"].value = ";".join([index.index_kit_i7.identifier for index in library.indices if index.index_kit_i7])
                    active_sheet[f"{column_mapping['kit_i5']}{i + 2}"].value = ";".join([index.index_kit_i5.identifier for index in library.indices if index.index_kit_i5])
                    active_sheet[f"{column_mapping['index_well']}{i + 2}"].value = next(iter(barcode_table[barcode_table["library_id"] == library.id]["index_well"].tolist()), None)

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
