from typing import Optional

from flask import Response, url_for, flash, current_app
from flask_htmx import make_response
from wtforms import BooleanField

from opengsync_db import models
from opengsync_db.categories import IndexType, BarcodeType

from .. import db, logger, update_index_kits  # noqa
from ..tools import utils
from ..tools.spread_sheet_components import TextColumn, DuplicateCellValue, MissingCellValue, SpreadSheetColumn
from .HTMXFlaskForm import HTMXFlaskForm
from .SpreadsheetInput import SpreadsheetInput


class EditDualIndexKitBarcodesForm(HTMXFlaskForm):
    _template_path = "forms/edit_kit_barcodes.html"

    columns: list[SpreadSheetColumn] = [
        TextColumn("well", "Well", 100, max_length=8, clean_up_fnc=lambda x: utils.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
        TextColumn("name_i7", "Name i7", 150, max_length=models.LibraryIndex.name_i7.type.length, clean_up_fnc=lambda x: utils.make_alpha_numeric(x, replace_white_spaces_with="")),
        TextColumn("sequence_i7", "Sequence i7", 200, max_length=models.LibraryIndex.sequence_i7.type.length, clean_up_fnc=lambda x: utils.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
        TextColumn("name_i5", "Name i5", 150, max_length=models.LibraryIndex.name_i5.type.length, clean_up_fnc=lambda x: utils.make_alpha_numeric(x, replace_white_spaces_with="")),
        TextColumn("sequence_i5", "Sequence i5", 200, max_length=models.LibraryIndex.name_i5.type.length, clean_up_fnc=lambda x: utils.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
    ]

    rc_sequence_i7 = BooleanField("Reverse Complement i7", default=False)
    rc_sequence_i5 = BooleanField("Reverse Complement i5", default=False)

    def __init__(self, index_kit: models.IndexKit, formdata: Optional[dict] = None):
        super().__init__(formdata=formdata)
        self.index_kit = index_kit
        self._context["index_kit"] = index_kit

        if self.index_kit.type != IndexType.DUAL_INDEX:
            logger.error(f"Invalid index kit type: {self.index_kit.type}")
            raise ValueError("This form is only for dual index kits.")

        if formdata is None:
            csrf_token = self.csrf_token._value()  # type: ignore
        else:
            csrf_token = formdata.get("csrf_token")

        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=EditDualIndexKitBarcodesForm.columns, csrf_token=csrf_token,
            post_url="", formdata=formdata,
            df=db.get_index_kit_barcodes_df(self.index_kit.id, per_index=True),
            allow_new_rows=True
        )

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if not self.spreadsheet.validate():
            return False
        
        df = self.spreadsheet.df

        duplicate_well = df.duplicated(subset="well", keep=False)

        if self.index_kit.type == IndexType.DUAL_INDEX:
            df.loc[df["name_i5"].isna(), "name_i5"] = df.loc[df["name_i5"].isna(), "name_i7"]

        duplicated = df.duplicated(subset=["sequence_i7", "sequence_i5"], keep=False)

        for idx, row in df.iterrows():
            if row["well"] is None:
                self.spreadsheet.add_error(idx, "well", MissingCellValue("Well is missing."))
            elif duplicate_well.at[idx]:
                self.spreadsheet.add_error(idx, "well", DuplicateCellValue("Duplicate well."))

            if row["name_i7"] is None:
                self.spreadsheet.add_error(idx, "name_i7", MissingCellValue("Name i7 is missing."))
            if row["sequence_i7"] is None:
                self.spreadsheet.add_error(idx, "sequence_i7", MissingCellValue("Sequence i7 is missing."))
            if row["name_i5"] is None:
                self.spreadsheet.add_error(idx, "name_i5", MissingCellValue("Name i5 is missing."))
            if row["sequence_i5"] is None:
                self.spreadsheet.add_error(idx, "sequence_i5", MissingCellValue("Sequence i5 is missing."))

            if duplicated.at[idx]:
                self.spreadsheet.add_error(idx, "sequence_i7", DuplicateCellValue("Duplicate sequence combination i7 & i5."))
                self.spreadsheet.add_error(idx, "sequence_i5", DuplicateCellValue("Duplicate sequence combination i7 & i5"))

            for _idx, _ in df[(row["name_i7"] == df["name_i7"]) & (row["sequence_i7"] != df["sequence_i7"])].iterrows():
                self.spreadsheet.add_error(_idx, "name_i7", DuplicateCellValue("Duplicate name i7 with different sequence."))
            
            for _idx, _ in df[(row["name_i7"] != df["name_i7"]) & (row["sequence_i7"] == df["sequence_i7"])].iterrows():
                self.spreadsheet.add_error(_idx, "sequence_i7", DuplicateCellValue("Duplicate sequence i7 with different name."))

            for _idx, _ in df[(row["name_i5"] == df["name_i5"]) & (row["sequence_i5"] != df["sequence_i5"])].iterrows():
                self.spreadsheet.add_error(_idx, "name_i5", DuplicateCellValue("Duplicate name i5 with different sequence."))

            for _idx, _ in df[(row["name_i5"] != df["name_i5"]) & (row["sequence_i5"] == df["sequence_i5"])].iterrows():
                self.spreadsheet.add_error(_idx, "sequence_i5", DuplicateCellValue("Duplicate sequence i5 with different name."))

        if len(self.spreadsheet._errors) > 0:
            return False
        
        self.df = df

        return True

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        self.index_kit = db.remove_all_barcodes_from_kit(self.index_kit.id)
        self.df["barcode_i7_id"] = None
        self.df["barcode_i5_id"] = None

        for idx, row in self.df.iterrows():
            adapter = db.create_adapter(
                index_kit_id=self.index_kit.id,
                well=row["well"],
            )
            db.create_barcode(
                name=row["name_i7"],
                sequence=row["sequence_i7"] if not self.rc_sequence_i7.data else models.Barcode.reverse_complement(row["sequence_i7"]),
                well=row["well"],
                adapter_id=adapter.id,
                type=BarcodeType.INDEX_I7,
            )
            db.create_barcode(
                name=row["name_i5"],
                sequence=row["sequence_i5"] if not self.rc_sequence_i5.data else models.Barcode.reverse_complement(row["sequence_i5"]),
                well=row["well"],
                adapter_id=adapter.id,
                type=BarcodeType.INDEX_I5,
            )

        update_index_kits(db, current_app.config["APP_DATA_FOLDER"], types=[IndexType.DUAL_INDEX])
        flash("Changes saved!", "success")
        db.refresh(self.index_kit)
        return make_response(redirect=(url_for("kits_page.index_kit", index_kit_id=self.index_kit.id)))
    

class EditSingleIndexKitBarcodesForm(HTMXFlaskForm):
    _template_path = "forms/edit_kit_barcodes.html"
    
    columns = [
        SpreadSheetColumn("well", "Well", "text", 100, str, clean_up_fnc=lambda x: utils.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
        SpreadSheetColumn("name", "Name", "text", 150, str, clean_up_fnc=lambda x: utils.make_alpha_numeric(x, replace_white_spaces_with="")),
        SpreadSheetColumn("sequence_i7", "Sequence", "text", 300, str, clean_up_fnc=lambda x: utils.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
    ]

    rc_sequence = BooleanField("Reverse Complement Sequences", default=False)

    def __init__(self, index_kit: models.IndexKit, formdata: Optional[dict] = None):
        super().__init__(formdata=formdata)
        self.index_kit = index_kit
        self._context["index_kit"] = index_kit

        if self.index_kit.type != IndexType.SINGLE_INDEX:
            logger.error(f"Invalid index kit type: {self.index_kit.type}")
            raise ValueError("This form is only for single index kits.")

        if formdata is None:
            csrf_token = self.csrf_token._value()  # type: ignore
        else:
            csrf_token = formdata.get("csrf_token")

        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=self.columns, csrf_token=csrf_token,
            post_url="", formdata=formdata,
            df=db.get_index_kit_barcodes_df(self.index_kit.id, per_index=True),
            allow_new_rows=True
        )

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if not self.spreadsheet.validate():
            return False
        
        df = self.spreadsheet.df

        df.loc[self.df["well"].notna(), "well"] = self.df.loc[self.df["well"].notna(), "well"].str.strip().str.replace(r'(?<=[A-Z])0+(?=\d)', '', regex=True)

        duplicate_well = df.duplicated(subset="well", keep=False)

        if self.index_kit.type == IndexType.DUAL_INDEX:
            df.loc[df["name_i5"].isna(), "name_i5"] = df.loc[df["name_i5"].isna(), "name_i7"]

        for idx, row in df.iterrows():
            if row["well"] is None:
                self.spreadsheet.add_error(idx, "well", DuplicateCellValue("Well is missing."))
            elif duplicate_well.at[idx]:
                self.spreadsheet.add_error(idx, "well", DuplicateCellValue("Duplicate well."))

            if row["name"] is None:
                self.spreadsheet.add_error(idx, "name", MissingCellValue("Name is missing."))
            if row["sequence_i7"] is None:
                self.spreadsheet.add_error(idx, "sequence_i7", MissingCellValue("Sequence is missing."))
            
            if (row["name"] == df["name"]).sum() > 1:
                self.spreadsheet.add_error(idx, "name", DuplicateCellValue("Duplicate name."))
            if (row["sequence_i7"] == df["sequence_i7"]).sum() > 1:
                self.spreadsheet.add_error(idx, "sequence_i7", DuplicateCellValue("Duplicate sequence."))

        if len(self.spreadsheet._errors) > 0:
            return False
        
        self.df = df

        return True
    
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        self.index_kit = db.remove_all_barcodes_from_kit(self.index_kit.id)

        for idx, row in self.df.iterrows():
            adapter = db.create_adapter(
                index_kit_id=self.index_kit.id,
                well=row["well"],
            )
            db.create_barcode(
                name=row["name"],
                sequence=row["sequence_i7"] if not self.rc_sequence.data else models.Barcode.reverse_complement(row["sequence_i7"]),
                well=row["well"],
                adapter_id=adapter.id,
                type=BarcodeType.INDEX_I7,
            )
        
        update_index_kits(db, current_app.config["APP_DATA_FOLDER"], types=[IndexType.SINGLE_INDEX])
        flash("Changes saved!", "success")
        return make_response(redirect=(url_for("kits_page.index_kit", index_kit_id=self.index_kit.id)))
    

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

    def __init__(self, index_kit: models.IndexKit, formdata: Optional[dict] = None):
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
            df=db.get_index_kit_barcodes_df(self.index_kit.id, per_index=True),
            allow_new_rows=True
        )

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if not self.spreadsheet.validate():
            return False
        
        df = self.spreadsheet.df

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
        
        self.index_kit = db.remove_all_barcodes_from_kit(self.index_kit.id)

        for idx, row in self.df.iterrows():
            adapter = db.create_adapter(
                index_kit_id=self.index_kit.id,
                well=row["well"],
            )
            for i in range(4):
                db.create_barcode(
                    name=row["name"],
                    sequence=row[f"sequence_{i + 1}"] if not self.rc_sequence.data else models.Barcode.reverse_complement(row[f"sequence_{i + 1}"]),
                    well=row["well"],
                    adapter_id=adapter.id,
                    type=BarcodeType.INDEX_I7,
                )
        
        update_index_kits(db, current_app.config["APP_DATA_FOLDER"], types=[IndexType.TENX_ATAC_INDEX])
        flash("Changes saved!", "success")
        return make_response(redirect=(url_for("kits_page.index_kit", index_kit_id=self.index_kit.id)))
        
