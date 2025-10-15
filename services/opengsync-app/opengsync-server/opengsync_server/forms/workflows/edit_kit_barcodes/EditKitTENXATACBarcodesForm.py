from flask import Response, url_for, flash
from flask_htmx import make_response
from wtforms import BooleanField

from opengsync_db import models
from opengsync_db.categories import IndexType, BarcodeType

from .... import db, logger  # noqa
from ....core.RunTime import runtime
from ....tools import utils
from ....tools.spread_sheet_components import TextColumn, DuplicateCellValue, MissingCellValue, SpreadSheetColumn
from ...HTMXFlaskForm import HTMXFlaskForm
from ...SpreadsheetInput import SpreadsheetInput

class EditKitTENXATACBarcodesForm(HTMXFlaskForm):
    _template_path = "forms/edit_kit_barcodes.html"

    rc_sequence = BooleanField("Reverse Complement Sequences", default=False)

    columns = [
        SpreadSheetColumn("well", "Well", "text", 100, str, clean_up_fnc=lambda x: utils.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
        SpreadSheetColumn("name", "Name", "text", 150, str, clean_up_fnc=lambda x: utils.make_alpha_numeric(x, replace_white_spaces_with="")),
        SpreadSheetColumn("sequence_2", "Sequence 2", "text", 200, str, clean_up_fnc=lambda x: utils.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
        SpreadSheetColumn("sequence_1", "Sequence 1", "text", 200, str, clean_up_fnc=lambda x: utils.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
        SpreadSheetColumn("sequence_3", "Sequence 3", "text", 200, str, clean_up_fnc=lambda x: utils.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
        SpreadSheetColumn("sequence_4", "Sequence 4", "text", 200, str, clean_up_fnc=lambda x: utils.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
    ]

    def __init__(self, index_kit: models.IndexKit, formdata: dict | None = None):
        super().__init__(formdata=formdata)
        self.index_kit = index_kit
        self._context["index_kit"] = index_kit

        if self.index_kit.type != IndexType.TENX_ATAC_INDEX:
            logger.error(f"Invalid index kit type: {self.index_kit.type}")
            raise ValueError("This form is only for TENX ATAC index kits.")
        
        if formdata is None:
            csrf_token = self.csrf_token._value()  # type: ignore
        else:
            csrf_token = formdata.get("csrf_token")

        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=self.columns, csrf_token=csrf_token,
            post_url="", formdata=formdata,
            df=db.pd.get_index_kit_barcodes(self.index_kit.id, per_index=True),
            allow_new_rows=True
        )

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if not self.spreadsheet.validate():
            return False
        
        df = self.spreadsheet.df
        df.loc[df["well"].notna(), "well"] = df.loc[df["well"].notna(), "well"].str.strip().str.replace(r'(?<=[A-Z])0+(?=\d)', '', regex=True)

        duplicate_well = df.duplicated(subset="well", keep=False)

        if self.index_kit.type == IndexType.DUAL_INDEX:
            df.loc[df["name_i5"].isna(), "name_i5"] = df.loc[df["name_i5"].isna(), "name_i7"]

        for idx, row in df.iterrows():
            if row["well"] is None:
                self.spreadsheet.add_error(idx, "well", MissingCellValue("Well is missing."))
            elif duplicate_well.at[idx]:
                self.spreadsheet.add_error(idx, "well", DuplicateCellValue("Duplicate well."))
            
            if row["name"] is None:
                self.spreadsheet.add_error(idx, "name", MissingCellValue("Name is missing."))
            if row["sequence_1"] is None:
                self.spreadsheet.add_error(idx, "sequence_1", MissingCellValue("Sequence 1 is missing."))
            if row["sequence_2"] is None:
                self.spreadsheet.add_error(idx, "sequence_2", MissingCellValue("Sequence 2 is missing."))
            if row["sequence_3"] is None:
                self.spreadsheet.add_error(idx, "sequence_3", MissingCellValue("Sequence 3 is missing."))
            if row["sequence_4"] is None:
                self.spreadsheet.add_error(idx, "sequence_4", MissingCellValue("Sequence 4 is missing."))

            # TODO: Check for duplicates

        if len(self.spreadsheet._errors) > 0:
            return False
        
        self.df = df

        return True

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        self.index_kit = db.index_kits.remove_all_barcodes(self.index_kit.id)

        for idx, row in self.df.iterrows():
            adapter = db.adapters.create(
                index_kit_id=self.index_kit.id,
                well=row["well"],
            )
            for i in range(4):
                db.barcodes.create(
                    name=row["name"],
                    sequence=row[f"sequence_{i + 1}"] if not self.rc_sequence.data else models.Barcode.reverse_complement(row[f"sequence_{i + 1}"]),
                    well=row["well"],
                    adapter_id=adapter.id,
                    type=BarcodeType.INDEX_I7,
                )
        
        utils.update_index_kits(db, runtime.app.app_data_folder, types=[IndexType.TENX_ATAC_INDEX])
        flash("Changes saved!", "success")
        return make_response(redirect=(url_for("kits_page.index_kit", index_kit_id=self.index_kit.id)))