import pandas as pd

from flask import Response, url_for, flash
from flask_htmx import make_response

from opengsync_db import models
from opengsync_db.categories import LibraryType, IndexType

from .... import logger, db  # noqa F401

from ....tools.spread_sheet_components import DropdownColumn, InvalidCellValue, IntegerColumn
from .IndexKitMappingForm import IndexKitMappingForm
from ..common import CommonBarcodeInputForm


class BarcodeInputForm(CommonBarcodeInputForm):
    _template_path = "workflows/reindex/barcode-input.html"
    _workflow_name = "reindex"

    def __init__(
        self,
        seq_request: models.SeqRequest | None,
        lab_prep: models.LabPrep | None,
        pool: models.Pool | None,
        formdata: dict | None,
        uuid: str | None
    ):
        CommonBarcodeInputForm.__init__(
            self, uuid=uuid, workflow=BarcodeInputForm._workflow_name,
            formdata=formdata,
            pool=pool, lab_prep=lab_prep, seq_request=seq_request,
            additional_columns=[
                IntegerColumn("library_id", "Library ID", 100, required=True, read_only=True),
                DropdownColumn("library_name", "Library Name", 250, choices=[], required=True, read_only=True),
            ]
        )

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        for idx, row in self.df.iterrows():
            if row["library_id"] not in self.library_table["library_id"].values:
                self.spreadsheet.add_error(idx, "library_id", InvalidCellValue("invalid 'library_id'"))
            else:
                try:
                    _id = int(row["library_id"])
                except ValueError:
                    self.spreadsheet.add_error(idx, "library_id", InvalidCellValue("invalid 'library_id'"))
                    continue
                if (library := db.get_library(_id)) is None:
                    self.spreadsheet.add_error(idx, "library_id", InvalidCellValue("invalid 'library_id'"))
                elif library.name != row["library_name"]:
                    self.spreadsheet.add_error(idx, "library_name", InvalidCellValue("invalid 'library_name' for 'library_id'"))
                elif self.lab_prep is not None and library.lab_prep_id != self.lab_prep.id:
                    self.spreadsheet.add_error(idx, "library_id", InvalidCellValue("Library is not part of this lab prep"))
                elif self.seq_request is not None and library.seq_request_id != self.seq_request.id:
                    self.spreadsheet.add_error(idx, "library_id", InvalidCellValue("Library is not part of this sequencing request"))
                
                if self.library_table[self.library_table["library_id"] == row["library_id"]]["library_name"].isin([row["library_name"]]).all() == 0:
                    self.spreadsheet.add_error(idx, "library_name", InvalidCellValue("invalid 'library_name' for 'library_id'"))

        return len(self.spreadsheet._errors) == 0

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        barcode_table = self.get_barcode_table()
        self.update_table("library_table", self.df)

        if IndexKitMappingForm.is_applicable(self):
            self.add_table("barcode_table", barcode_table)
            self.update_data()
            form = IndexKitMappingForm(uuid=self.uuid, lab_prep=self.lab_prep, seq_request=self.seq_request, pool=self.pool, formdata=None)
            return form.make_response()
        
        for _, row in self.library_table.iterrows():
            if (library := db.get_library(row["library_id"])) is None:
                logger.error(f"{self.uuid}: Library {row['library_id']} not found")
                raise ValueError(f"{self.uuid}: Library {row['library_id']} not found")

            library = db.remove_library_indices(library_id=library.id)
            df = barcode_table[barcode_table[self.index_col] == row[self.index_col]].copy()

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

        flash("Libraries Re-Indexed!")
        if self.seq_request is not None:
            return make_response(redirect=url_for("seq_requests_page.seq_request", seq_request_id=self.seq_request.id))
        
        if self.lab_prep is not None:
            return make_response(redirect=url_for("lab_preps_page.lab_prep", lab_prep_id=self.lab_prep.id))
        
        if self.pool is not None:
            return make_response(redirect=url_for("pools_page.pool", pool_id=self.pool.id))
        
        return make_response(redirect=url_for("dashboard"))