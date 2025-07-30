import pandas as pd

from flask import Response, url_for, flash
from flask_htmx import make_response

from opengsync_db import models
from opengsync_db.categories import LibraryType, IndexType

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
        self.barcode_table = tools.check_indices(self.tables["barcode_table"])
        self.library_table = self.tables["library_table"]
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
        for _, row in self.library_table.iterrows():
            if (library := db.get_library(row["library_id"])) is None:
                logger.error(f"{self.uuid}: Library {row['library_id']} not found")
                raise ValueError(f"{self.uuid}: Library {row['library_id']} not found")

            library = db.remove_library_indices(library_id=library.id)
            df = self.barcode_table[self.barcode_table[self.index_col] == row[self.index_col]].copy()

            seq_i7s = df["sequence_i7"].values
            seq_i5s = df["sequence_i5"].values
            name_i7s = df["name_i7"].values
            name_i5s = df["name_i5"].values

            if library.type == LibraryType.TENX_SC_ATAC:
                if len(df) != 4:
                    logger.warning(f"{self.uuid}: Expected 4 barcodes (i7) for TENX_SC_ATAC library, found {len(df)}.")
                index_type = IndexType.TENX_ATAC_INDEX
            else:
                if df["sequence_i5"].isna().all():
                    index_type = IndexType.SINGLE_INDEX
                elif df["sequence_i5"].isna().any():
                    logger.warning(f"{self.uuid}: Mixed index types found for library {df['library_name']}.")
                    index_type = IndexType.DUAL_INDEX
                else:
                    index_type = IndexType.DUAL_INDEX

            library.index_type = index_type
            library = db.update_library(library)

            for j in range(max(len(seq_i7s), len(seq_i5s))):
                library = db.add_library_index(
                    library_id=library.id,
                    index_kit_i7_id=None,
                    index_kit_i5_id=None,
                    name_i7=name_i7s[j] if len(name_i7s) > j and pd.notna(name_i7s[j]) else None,
                    name_i5=name_i5s[j] if len(name_i5s) > j and pd.notna(name_i5s[j]) else None,
                    sequence_i7=seq_i7s[j] if len(seq_i7s) > j and pd.notna(seq_i7s[j]) else None,
                    sequence_i5=seq_i5s[j] if len(seq_i5s) > j and pd.notna(seq_i5s[j]) else None,
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
        