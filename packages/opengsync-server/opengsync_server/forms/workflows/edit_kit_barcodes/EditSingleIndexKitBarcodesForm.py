from flask import Response, url_for, flash
from flask_htmx import make_response
from wtforms import BooleanField

from opengsync_db import models, queries as Q
from opengsync_db.categories import IndexType, BarcodeType

from .... import db, logger
from ....core.RunTime import runtime
from ....tools import utils
from ....tools.spread_sheet_components import DuplicateCellValue, MissingCellValue, SpreadSheetColumn
from ...HTMXFlaskForm import HTMXFlaskForm
from ...SpreadsheetInput import SpreadsheetInput


class EditSingleIndexKitBarcodesForm(HTMXFlaskForm):
    _template_path = "forms/edit_kit_barcodes.html"
    
    columns = [
        SpreadSheetColumn("well", "Well", "text", 100, str, clean_up_fnc=lambda x: utils.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
        SpreadSheetColumn("name", "Name", "text", 150, str, clean_up_fnc=lambda x: utils.make_alpha_numeric(x, replace_white_spaces_with="")),
        SpreadSheetColumn("sequence", "Sequence", "text", 300, str, clean_up_fnc=lambda x: utils.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
    ]

    rc_sequence = BooleanField("Reverse Complement Sequences", default=False)

    def __init__(self, index_kit: models.IndexKit, formdata: dict | None = None):
        super().__init__(formdata=formdata)
        self.index_kit = index_kit
        self._context["index_kit"] = index_kit

        match self.index_kit.type:
            case IndexType.SINGLE_INDEX_I7:
                df = db.pd.get_index_kit_barcodes(self.index_kit.id, per_index=True).rename(columns={"sequence_i7": "sequence", "name_i7": "name"})
            case _:
                logger.error(f"Invalid index kit type: {self.index_kit.type}")
                raise ValueError("This form is only for single index kits.")

        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=self.columns, csrf_token=self._csrf_token,
            post_url="", formdata=formdata, df=df,
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

        for idx, row in df.iterrows():
            if row["well"] is None:
                self.spreadsheet.add_error(idx, "well", DuplicateCellValue("Well is missing."))
            elif duplicate_well.at[idx]:
                self.spreadsheet.add_error(idx, "well", DuplicateCellValue("Duplicate well."))

            if row["name"] is None:
                self.spreadsheet.add_error(idx, "name", MissingCellValue("Name is missing."))
            if row["sequence"] is None:
                self.spreadsheet.add_error(idx, "sequence", MissingCellValue("Sequence is missing."))
            
            if (row["name"] == df["name"]).sum() > 1:
                self.spreadsheet.add_error(idx, "name", DuplicateCellValue("Duplicate name."))
            if (row["sequence"] == df["sequence"]).sum() > 1:
                self.spreadsheet.add_error(idx, "sequence", DuplicateCellValue("Duplicate sequence."))

        if len(self.spreadsheet._errors) > 0:
            return False
        
        self.df = df

        return True
    
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        self.index_kit = db.actions.remove_all_barcodes_from_kit(self.index_kit)

        barcodes = []
        for _, row in self.df.iterrows():
            adapter = Q.adapter.create(
                index_kit=self.index_kit,
                well=row["well"],
            )
            barcodes.append(Q.barcode.create(
                name=row["name"],
                sequence=row["sequence"] if not self.rc_sequence.data else models.Barcode.reverse_complement(row["sequence"]),
                well=row["well"],
                adapter=adapter,
                type=BarcodeType.INDEX_I7,
            ))

        db.session.add_all(barcodes)
        
        flash("Changes saved!", "success")
        return make_response(redirect=(url_for("kits_page.index_kit", index_kit_id=self.index_kit.id)))