import pandas as pd

from flask import Response, url_for, flash
from flask_htmx import make_response

from opengsync_db import models
from opengsync_db.categories import LibraryType, IndexType, BarcodeOrientation

from .... import logger, db  # noqa F401
from .... import logger, tools, db  # noqa F401
from ...MultiStepForm import MultiStepForm


class CompleteReindexForm(MultiStepForm):
    _template_path = "workflows/reindex/reindex-complete.html"
    _workflow_name = "reindex"
    _step_name = "complete_reindex"

    def __init__(
        self,
        seq_request: models.SeqRequest | None,
        lab_prep: models.LabPrep | None,
        pool: models.Pool | None,
        formdata: dict | None,
        uuid: str | None
    ):
        MultiStepForm.__init__(
            self, workflow=CompleteReindexForm._workflow_name,
            formdata=formdata, step_name=CompleteReindexForm._step_name,
            uuid=uuid, step_args={"seq_request": seq_request, "lab_prep": lab_prep, "pool": pool},
        )
        self.seq_request = seq_request
        self.lab_prep = lab_prep
        self.pool = pool
        self.library_table = self.tables["library_table"]
        self.barcode_table = self.tables["barcode_table"]
        self.barcode_table["orientation_id"] = self.barcode_table["orientation_i7_id"]
        self.barcode_table.loc[
            pd.notna(self.barcode_table["orientation_i7_id"]) &
            (self.barcode_table["orientation_i7_id"] != self.barcode_table["orientation_i5_id"]),
            "orientation_id"
        ] = None
        self.barcode_table = tools.check_indices(self.barcode_table)
        self.index_col = self.metadata["index_col"]
        self._context["barcode_table"] = self.barcode_table

        self.url_context = {}
        if seq_request is not None:
            self._context["seq_request"] = seq_request
            self.url_context["seq_request_id"] = seq_request.id
        if lab_prep is not None:
            self._context["lab_prep"] = lab_prep
            self.url_context["lab_prep_id"] = lab_prep.id
        if pool is not None:
            self._context["pool"] = pool
            self.url_context["pool_id"] = pool.id

        self.post_url = url_for("reindex_workflow.complete_reindex", uuid=self.uuid, **self.url_context)

    def process_request(self) -> Response:
        for _, library_row in self.library_table.iterrows():
            if (library := db.libraries.get(library_row["library_id"])) is None:
                logger.error(f"{self.uuid}: Library {library_row['library_id']} not found")
                raise ValueError(f"{self.uuid}: Library {library_row['library_id']} not found")

            library = db.libraries.remove_indices(library_id=library.id)
            library_barcodes = self.barcode_table[self.barcode_table[self.index_col] == library_row[self.index_col]].copy()

            if library.type == LibraryType.TENX_SC_ATAC:
                if len(library_barcodes) != 4:
                    logger.warning(f"{self.uuid}: Expected 4 barcodes (i7) for TENX_SC_ATAC library, found {len(library_barcodes)}.")
                index_type = IndexType.TENX_ATAC_INDEX
            else:
                if library_barcodes["sequence_i5"].isna().all():
                    index_type = IndexType.SINGLE_INDEX_I7
                elif library_barcodes["sequence_i5"].isna().any():
                    logger.warning(f"{self.uuid}: Mixed index types found for library {library_row['library_name']}.")
                    index_type = IndexType.DUAL_INDEX
                else:
                    index_type = IndexType.DUAL_INDEX

            library.index_type = index_type
            db.libraries.update(library)

            for _, barcode_row in library_barcodes.iterrows():
                if int(barcode_row["index_type_id"]) != index_type.id:
                    logger.error(f"{self.uuid}: Index type mismatch for library {library_row['library_name']}. Expected {index_type}, found {IndexType.get(barcode_row['index_type_id'])}.")

                orientation = None
                if pd.notna(barcode_row["orientation_i7_id"]):
                    orientation = BarcodeOrientation.get(int(barcode_row["orientation_i7_id"]))

                if orientation is not None and pd.notna(barcode_row["orientation_i5_id"]):
                    if orientation.id != int(barcode_row["orientation_i5_id"]):
                        logger.error(f"{self.uuid}: Conflicting orientations for i7 and i5 in library {library_row['library_name']}.")
                        raise ValueError("Conflicting orientations for i7 and i5.")

                library = db.libraries.add_index(
                    library_id=library.id,
                    sequence_i7=barcode_row["sequence_i7"] if pd.notna(barcode_row["sequence_i7"]) else None,
                    sequence_i5=barcode_row["sequence_i5"] if pd.notna(barcode_row["sequence_i5"]) else None,
                    index_kit_i7_id=barcode_row["kit_i7_id"] if pd.notna(barcode_row["kit_i7_id"]) else None,
                    index_kit_i5_id=barcode_row["kit_i5_id"] if pd.notna(barcode_row["kit_i5_id"]) else None,
                    name_i7=barcode_row["name_i7"] if pd.notna(barcode_row["name_i7"]) else None,
                    name_i5=barcode_row["name_i5"] if pd.notna(barcode_row["name_i5"]) else None,
                    orientation=orientation,
                )

        flash("Libraries Re-Indexed!", "success")
        self.complete()
        
        if self.seq_request is not None:
            return make_response(redirect=url_for("seq_requests_page.seq_request", seq_request_id=self.seq_request.id))
        if self.lab_prep is not None:
            return make_response(redirect=url_for("lab_preps_page.lab_prep", lab_prep_id=self.lab_prep.id))
        if self.pool is not None:
            return make_response(redirect=url_for("pools_page.pool", pool_id=self.pool.id))
        
        return make_response(redirect=url_for("dashboard"))
        