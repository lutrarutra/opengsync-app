import pandas as pd

from flask import Response, url_for, flash
from flask_htmx import make_response

from opengsync_db import models
from opengsync_db.categories import FeatureType

from .. import logger, db, tools
from ..tools.spread_sheet_components import TextColumn, CategoricalDropDown, DropdownColumn, DuplicateCellValue, InvalidCellValue, MissingCellValue
from .HTMXFlaskForm import HTMXFlaskForm
from .SpreadsheetInput import SpreadsheetInput


class LibraryFeaturesForm(HTMXFlaskForm):
    _template_path = "forms/library-features-table.html"

    def __init__(self, library: models.Library, formdata: dict | None = None):
        super().__init__(formdata=formdata)
        self.library = library
        self._context["library"] = library

        self.kits_mapping = {kit.identifier: f"[{kit.identifier}] {kit.name}" for kit in db.feature_kits.find(limit=None, sort_by="name", type=FeatureType.ANTIBODY)[0]}

        columns = [
            CategoricalDropDown("kit", "Kit", 250, categories=self.kits_mapping, required=False),
            TextColumn("identifier", "Identifier", 150, max_length=models.Feature.identifier.type.length, required=True, clean_up_fnc=tools.utils.normalize_to_ascii, validation_fnc=tools.utils.check_string),
            TextColumn("feature", "Feature", 150, max_length=models.Feature.name.type.length),
            TextColumn("sequence", "Sequence", 150, max_length=models.Feature.sequence.type.length, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
            TextColumn("pattern", "Pattern", 200, max_length=models.Feature.pattern.type.length),
            DropdownColumn("read", "Read", 100, choices=["R2", "R1"]),
        ]

        df = db.pd.get_library_features(library.id).rename(columns={
            "feature_name": "feature",
            "kit_identifier": "kit",
        })

        self.spreadsheet = SpreadsheetInput(
            columns=columns, csrf_token=self._csrf_token,
            post_url=url_for('libraries_htmx.edit_features', library_id=library.id),
            formdata=formdata, allow_new_rows=True, allow_new_cols=False, df=df
        )

    def validate(self) -> bool:
        if not super().validate():
            return False
            
        if not self.spreadsheet.validate():
            return False
    
        self.df = self.spreadsheet.df
        
        kit_feature = pd.notna(self.df["kit"])
        custom_feature = pd.notna(self.df["feature"]) & pd.notna(self.df["sequence"]) & pd.notna(self.df["pattern"]) & pd.notna(self.df["read"])
        duplicate_identifier = pd.notna(self.df["identifier"]) & self.df.duplicated(subset=["identifier"], keep=False)
        duplicate_name = pd.notna(self.df["feature"]) & self.df.duplicated(subset=["feature"], keep=False)
        duplicated = self.df.duplicated(keep=False)

        kit_identifiers = self.df["kit"].dropna().unique().tolist()
        self.kits: dict[str, tuple[models.FeatureKit, pd.DataFrame]] = dict()
        
        self.df["kit_id"] = pd.Series([None] * len(self.df), dtype="Int64")
        self.df["feature_id"] = None
        for identifier in kit_identifiers:
            kit = db.feature_kits[identifier]
            kit_df = db.pd.get_feature_kit_features(kit.id)
            self.kits[identifier] = (kit, kit_df)
            self.df.loc[self.df["kit"] == identifier, "kit_id"] = kit.id

        for identifier, (kit, kit_df) in self.kits.items():
            view = self.df[self.df["kit"] == identifier]
            mask = kit_df["name"].isin(view["feature"])

            for _, kit_row in kit_df[mask].iterrows():
                self.df.loc[
                    (self.df["kit"] == identifier) & (self.df["feature"] == kit_row["name"]),
                    ["sequence", "pattern", "read"]
                ] = kit_row[["sequence", "pattern", "read"]].values

                self.df.loc[
                    (self.df["kit"] == identifier) & (self.df["identifier"] == kit_row["identifier"]),
                    ["sequence", "pattern", "read"]
                ] = kit_row[["sequence", "pattern", "read"]].values

        for idx, row in self.df.iterrows():
            if duplicate_identifier.at[idx]:
                self.spreadsheet.add_error(idx, "identifier", DuplicateCellValue("duplicate feature definition"))

            if duplicate_name.at[idx]:
                self.spreadsheet.add_error(idx, "feature", DuplicateCellValue("duplicate feature name"))

            if duplicated.at[idx]:
                self.spreadsheet.add_error(idx, "kit", DuplicateCellValue("duplicate feature definition"))
                self.spreadsheet.add_error(idx, "feature", DuplicateCellValue("duplicate feature definition"))
                self.spreadsheet.add_error(idx, "sequence", DuplicateCellValue("duplicate feature definition"))
                self.spreadsheet.add_error(idx, "pattern", DuplicateCellValue("duplicate feature definition"))
                self.spreadsheet.add_error(idx, "read", DuplicateCellValue("duplicate feature definition"))

            if kit_feature.at[idx]:
                identifier = row["kit"]
                kit, kit_df = self.kits[identifier]
                if pd.notna(row["identifier"]):
                    if row["identifier"] not in kit_df["identifier"].values:
                        self.df.at[idx, "feature_id"] = kit_df.loc[kit_df["identifier"] == row["identifier"], "feature_id"].values[0]  # type: ignore
                        self.spreadsheet.add_error(idx, "identifier", InvalidCellValue(f"Identifier '{row['identifier']}' not found in kit '{identifier}'"))
                        continue
                if pd.notna(row["feature"]):
                    if row["feature"] not in kit_df["name"].values:
                        self.spreadsheet.add_error(idx, "feature", InvalidCellValue(f"Feature '{row['feature']}' not found in kit '{identifier}'"))
                        continue

            # Not defined custom nor kit feature
            elif (not custom_feature.at[idx] and not kit_feature.at[idx]):
                self.spreadsheet.add_error(idx, "kit", MissingCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."))
                self.spreadsheet.add_error(idx, "feature", MissingCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."))
                self.spreadsheet.add_error(idx, "sequence", MissingCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."))
                self.spreadsheet.add_error(idx, "pattern", MissingCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."))
                self.spreadsheet.add_error(idx, "read", MissingCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."))

            # Defined both custom and kit feature
            elif custom_feature.at[idx] and kit_feature.at[idx]:
                self.spreadsheet.add_error(idx, "kit", InvalidCellValue("must have either 'Kit' or 'Feature + Sequence + Pattern + Read' specified, not both."))
                self.spreadsheet.add_error(idx, "feature", InvalidCellValue("must have either 'Kit' or 'Feature + Sequence + Pattern + Read' specified, not both."))
                self.spreadsheet.add_error(idx, "sequence", InvalidCellValue("must have either 'Kit' or 'Feature + Sequence + Pattern + Read' specified, not both."))
                self.spreadsheet.add_error(idx, "pattern", InvalidCellValue("must have either 'Kit' or 'Feature + Sequence + Pattern + Read' specified, not both."))
                self.spreadsheet.add_error(idx, "read", InvalidCellValue("must have either 'Kit' or 'Feature + Sequence + Pattern + Read' specified, not both."))

            elif custom_feature.at[idx]:
                idx_sequence = self.df["sequence"] == row["sequence"]
                idx_pattern = self.df["pattern"] == row["pattern"]
                idx_read = self.df["read"] == row["read"]

                idx = idx_sequence & idx_pattern & idx_read

                if self.df[idx].shape[0] > 1:
                    self.spreadsheet.add_error(idx, "sequence", DuplicateCellValue("Duplicate 'Sequence + Pattern + Read' combination."))
                    self.spreadsheet.add_error(idx, "pattern", DuplicateCellValue("Duplicate 'Sequence + Pattern + Read' combination."))
                    self.spreadsheet.add_error(idx, "read", DuplicateCellValue("Duplicate 'Sequence + Pattern + Read' combination."))

            elif kit_feature.at[idx]:
                idx_kit = self.df["kit"] == row["kit"]
                idx_feature = self.df["feature"] == row["feature"]
                idx = True
                if pd.notna(row["kit"]):
                    idx = idx & idx_kit
                if pd.notna(row["feature"]):
                    idx = idx & idx_feature
                
                if self.df[idx].shape[0] > 1:
                    self.spreadsheet.add_error(idx, "feature", DuplicateCellValue("Duplicate 'Kit' + 'Feature' specified."))

        if (self.df["kit_id"].notna() & self.df["feature_id"].isna()).any() or (self.df["kit_id"].isna() & self.df["feature_id"].notna()).any():
            raise Exception("Logic error: kit_id and feature_id should be both NaN or both not NaN at this point.")

        if len(self.spreadsheet._errors) > 0:
            return False
        
        self.df = self.df
        return True
    
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        self.library.features = []
        for _, row in self.df.iterrows():
            if pd.notna(row["feature_id"]):
                if (feature := db.features.get(int(row["feature_id"]))) is None:
                    raise Exception(f"Feature '{row['feature']}' not found in kit '{row['kit_id']}'")
                self.library.features.append(feature)
            else:
                feature = db.features.create(
                    identifier=row["identifier"],
                    name=row["feature"],
                    sequence=row["sequence"],
                    pattern=row["pattern"],
                    read=row["read"],
                    type=FeatureType.ANTIBODY
                )
                self.library.features.append(feature)

        db.libraries.update(self.library)

        flash("Changes Saved!", "success")
        return make_response(redirect=url_for("libraries_page.library", library_id=self.library.id))
