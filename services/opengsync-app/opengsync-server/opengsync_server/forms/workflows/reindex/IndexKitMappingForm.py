from flask import Response

import pandas as pd

from flask import url_for, flash
from flask_htmx import make_response

from opengsync_db import models
from opengsync_db.categories import IndexType, LibraryType

from .... import db, logger
from ..common import CommonIndexKitMappingForm


class IndexKitMappingForm(CommonIndexKitMappingForm):
    _template_path = "workflows/reindex/index_kit-mapping.html"
    _workflow_name = "reindex"

    def __init__(
        self,
        seq_request: models.SeqRequest | None,
        lab_prep: models.LabPrep | None,
        pool: models.Pool | None,
        formdata: dict | None,
        uuid: str | None = None
    ):
        CommonIndexKitMappingForm.__init__(
            self, uuid=uuid, workflow=IndexKitMappingForm._workflow_name,
            formdata=formdata,
            pool=pool, lab_prep=lab_prep, seq_request=seq_request
        )
        
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        library_table = self.tables["library_table"]
        
        for _, row in library_table.iterrows():
            if (library := db.get_library(row["library_id"])) is None:
                logger.error(f"{self.uuid}: Library {row['library_id']} not found")
                raise ValueError(f"{self.uuid}: Library {row['library_id']} not found")

            library = db.remove_library_indices(library_id=library.id)
            df = self.barcode_table[self.barcode_table["library_name"] == row["library_name"]].copy()

            seq_i7s = df["sequence_i7"].values
            seq_i5s = df["sequence_i5"].values
            name_i7s = df["name_i7"].values
            name_i5s = df["name_i5"].values
            kit_i7_ids = df["kit_i7_id"].values
            kit_i5_ids = df["kit_i5_id"].values

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
                    index_kit_i7_id=kit_i7_ids[j] if len(kit_i7_ids) > j and pd.notna(kit_i7_ids[j]) else None,
                    index_kit_i5_id=kit_i5_ids[j] if len(kit_i5_ids) > j and pd.notna(kit_i5_ids[j]) else None,
                    name_i7=name_i7s[j] if len(name_i7s) > j and pd.notna(name_i7s[j]) else None,
                    name_i5=name_i5s[j] if len(name_i5s) > j and pd.notna(name_i5s[j]) else None,
                    sequence_i7=seq_i7s[j] if len(seq_i7s) > j and pd.notna(seq_i7s[j]) else None,
                    sequence_i5=seq_i5s[j] if len(seq_i5s) > j and pd.notna(seq_i5s[j]) else None,
                )

        self.complete()

        flash("Libraries Re-Indexed!", "success")
        if self.seq_request is not None:
            return make_response(redirect=url_for("seq_requests_page.seq_request_page", seq_request_id=self.seq_request.id))
        
        if self.lab_prep is not None:
            return make_response(redirect=url_for("lab_preps_page.lab_prep_page", lab_prep_id=self.lab_prep.id))
        
        if self.pool is not None:
            return make_response(redirect=url_for("pools_page.pool_page", pool_id=self.pool.id))
        
        return make_response(redirect=url_for("dashboard"))