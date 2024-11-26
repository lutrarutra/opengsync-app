from typing import Optional

import pandas as pd

from flask import Response, url_for, flash
from flask_htmx import make_response

from limbless_db import models
from limbless_db.categories import FeatureType

from .. import db, logger  # noqa
from ..tools import SpreadSheetColumn, tools
from .HTMXFlaskForm import HTMXFlaskForm
from .SpreadsheetInput import SpreadsheetInput


class EditKitFeaturesForm(HTMXFlaskForm):
    _template_path = "forms/edit_kit_features.html"

    columns = {
        "name": SpreadSheetColumn("A", "name", "Name", "text", 250, str),
        "sequence": SpreadSheetColumn("B", "sequence", "Sequence", "text", 150, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
        "pattern": SpreadSheetColumn("C", "pattern", "Pattern", "text", 200, str, clean_up_fnc=lambda x: x.strip() if pd.notna(x) else None),
        "read": SpreadSheetColumn("D", "read", "Read", "text", 100, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
        "target_name": SpreadSheetColumn("E", "target_name", "Target Name", "text", 200, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
        "target_id": SpreadSheetColumn("f", "target_id", "Target ID", "text", 200, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
    }

    def __init__(self, feature_kit: models.FeatureKit, formdata: Optional[dict] = None):
        super().__init__(formdata=formdata)
        self.feature_kit = feature_kit
        self._context["feature_kit"] = feature_kit

        if formdata is None:
            csrf_token = self.csrf_token._value()  # type: ignore
        else:
            csrf_token = formdata.get("csrf_token")

        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=self.columns, csrf_token=csrf_token,
            post_url=url_for("feature_kits_htmx.edit_features", feature_kit_id=feature_kit.id),
            formdata=formdata, df=self.__fill_form(), allow_new_rows=True
        )

    def __fill_form(self):
        template = db.get_feature_kit_features_df(self.feature_kit.id)
        return template[list(EditKitFeaturesForm.columns.keys())]

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if not self.spreadsheet.validate():
            return False
        
        df = self.spreadsheet.df

        duplicate_def = df.duplicated(subset=["sequence", "pattern", "read"], keep=False)
        duplicate_feature = df.duplicated(subset=["name"], keep=False) & (self.feature_kit.type in [FeatureType.CMO])

        for i, (idx, row) in enumerate(df.iterrows()):
            if pd.isna(row["name"]):
                self.spreadsheet.add_error(i + 1, "name", "Name cannot be empty.", "missing_value")
            elif duplicate_feature.at[idx]:
                self.spreadsheet.add_error(i + 1, "name", f"Duplicate feature name not allowed in '{self.feature_kit.type.name}'-kit.", "duplicate_value")
            if pd.isna(row["sequence"]):
                self.spreadsheet.add_error(i + 1, "sequence", "Sequence cannot be empty.", "missing_value")
            if pd.isna(row["pattern"]):
                self.spreadsheet.add_error(i + 1, "pattern", "Pattern cannot be empty.", "missing_value")
            if pd.isna(row["read"]):
                self.spreadsheet.add_error(i + 1, "read", "Read cannot be empty.", "missing_value")
            if duplicate_def.at[idx]:
                self.spreadsheet.add_error(i + 1, "sequence", "Duplicate sequence + pattern + read combination.", "duplicate_value")
                self.spreadsheet.add_error(i + 1, "pattern", "Duplicate sequence + pattern + read combination.", "duplicate_value")
                self.spreadsheet.add_error(i + 1, "read", "Duplicate sequence + pattern + read combination.", "duplicate_value")
        
        if len(self.spreadsheet._errors) > 0:
            return False
        
        self.df = df.sort_values("name")

        return True

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()

        self.feature_kit = db.remove_all_features_from_kit(self.feature_kit.id)
        for idx, row in self.df.iterrows():
            db.create_feature(
                name=row["name"],
                sequence=row["sequence"],
                pattern=row["pattern"],
                read=row["read"],
                target_name=row["target_name"] if pd.notna(row["target_name"]) else None,
                target_id=row["target_id"] if pd.notna(row["target_id"]) else None,
                feature_kit_id=self.feature_kit.id,
                type=self.feature_kit.type
            )
        
        flash("Changes saved!", "success")
        return make_response(redirect=(url_for("kits_page.feature_kit_page", feature_kit_id=self.feature_kit.id)))
        
