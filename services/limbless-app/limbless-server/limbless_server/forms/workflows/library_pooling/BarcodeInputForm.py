import os
import re
from typing import Optional

import pandas as pd

from flask import Response, current_app, url_for
from wtforms import SelectField, FormField
from flask_wtf import FlaskForm

from limbless_db import models

from .... import logger, tools, db  # noqa F401
from ....tools import SpreadSheetColumn
from ...MultiStepForm import MultiStepForm
from ...SpreadsheetInput import SpreadsheetInput
from ...SearchBar import OptionalSearchBar
from .IndexKitMappingForm import IndexKitMappingForm
from .CompleteLibraryPoolingForm import CompleteLibraryPoolingForm


class PlateSubForm(FlaskForm):
    index_kit = FormField(OptionalSearchBar, label="Select Index Kit")
    starting_index = SelectField("Starting Index", choices=[(i, models.Plate.well_identifier(i, 12, 8)) for i in range(96)], default=0, coerce=int)


def index_well_clean_up_fnc(x: str) -> str:
    well = re.sub(r"([a-zA-Z]+)0*(\d+)", r"\1\2", x)
    return well.upper()


class BarcodeInputForm(MultiStepForm):
    _template_path = "workflows/library_pooling/barcode-input.html"
    _workflow_name = "library_pooling"
    _step_name = "barcode_input"
    
    columns = [
        SpreadSheetColumn("library_id", "ID", "numeric", 50, int),
        SpreadSheetColumn("library_name", "Library Name", "text", 250, str),
        SpreadSheetColumn("index_well", "Index Well", "text", 70, str, clean_up_fnc=lambda x: index_well_clean_up_fnc(str(x)) if pd.notna(x) else None),
        SpreadSheetColumn("pool", "Pool", "text", 70, str),
        SpreadSheetColumn("kit_i7", "i7 Kit", "text", 200, str),
        SpreadSheetColumn("name_i7", "i7 Name", "text", 150, str),
        SpreadSheetColumn("sequence_i7", "i7 Sequence", "text", 180, str),
        SpreadSheetColumn("kit_i5", "i5 Kit", "text", 200, str),
        SpreadSheetColumn("name_i5", "i5 Name", "text", 150, str),
        SpreadSheetColumn("sequence_i5", "i5 Sequence", "text", 180, str),
    ]

    def __init__(self, lab_prep: models.LabPrep, formdata: dict = {}, uuid: Optional[str] = None):
        MultiStepForm.__init__(
            self, formdata=formdata, uuid=uuid, step_name=BarcodeInputForm._step_name,
            workflow=BarcodeInputForm._workflow_name, step_args={}
        )

        self.lab_prep = lab_prep
        self._context["lab_prep"] = lab_prep
        self._context["active_tab"] = "help"
        self.prep_libraries_df = db.get_lab_prep_libraries_df(lab_prep.id)

        if (csrf_token := formdata.get("csrf_token")) is None:
            csrf_token = self.csrf_token._value()  # type: ignore
        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=BarcodeInputForm.columns, csrf_token=csrf_token,
            post_url=url_for("library_pooling_workflow.parse_barcodes", lab_prep_id=lab_prep.id, uuid=self.uuid),
            formdata=formdata, df=self.get_template(),
        )

    def get_template(self) -> pd.DataFrame:
        if self.lab_prep.prep_file is not None:
            prep_table = pd.read_excel(os.path.join(current_app.config["MEDIA_FOLDER"], self.lab_prep.prep_file.path), "prep_table")  # type: ignore
            prep_table = prep_table.dropna(subset=["library_id", "library_name"])
            return prep_table[[col.label for col in BarcodeInputForm.columns]].copy()
        
        library_data = dict([(col.label, []) for col in BarcodeInputForm.columns])

        for library in self.lab_prep.libraries:
            library_data["library_id"].append(library.id)
            library_data["library_name"].append(library.name)
            library_data["index_well"].append(None)
            library_data["pool"].append(None)
            library_data["kit_i7"].append(None)
            library_data["name_i7"].append(library.names_i7_str(";"))
            library_data["sequence_i7"].append(library.sequences_i7_str(";"))
            library_data["kit_i5"].append(None)
            library_data["name_i5"].append(library.names_i5_str(";"))
            library_data["sequence_i5"].append(library.sequences_i5_str(";"))

        return pd.DataFrame(library_data)
    
    def validate(self) -> bool:
        validated = super().validate()
            
        if not validated:
            return False
        
        if not self.spreadsheet.validate():
            return False
        
        df = self.spreadsheet.df

        df.loc[df["kit_i7"].notna(), "kit_i7"] = df.loc[df["kit_i7"].notna(), "kit_i7"].astype(str)
        df.loc[df["kit_i5"].notna(), "kit_i5"] = df.loc[df["kit_i5"].notna(), "kit_i5"].astype(str)
        df["library_id"] = df["library_id"].astype(int)
            
        df["sequence_i7"] = df["sequence_i7"].apply(lambda x: tools.make_alpha_numeric(x, keep=[";"], replace_white_spaces_with=""))
        df["sequence_i5"] = df["sequence_i5"].apply(lambda x: tools.make_alpha_numeric(x, keep=[";"], replace_white_spaces_with=""))

        df.loc[df["index_well"].notna(), "index_well"] = df.loc[df["index_well"].notna(), "index_well"].str.strip().str.replace(r'(?<=[A-Z])0+(?=\d)', '', regex=True)

        kit_defined = df["kit_i7"].notna() & (df["index_well"].notna() | df["name_i7"].notna())
        manual_defined = df["sequence_i7"].notna()

        df.loc[df["kit_i5"].isna(), "kit_i5"] = df.loc[df["kit_i5"].isna(), "kit_i7"]
        df.loc[df["name_i5"].isna(), "name_i5"] = df.loc[df["name_i5"].isna(), "name_i7"]

        if df.loc[~df["pool"].astype(str).str.strip().str.lower().isin(["x", "t"]), "pool"].isna().all():
            df.loc[df["pool"].isna(), "pool"] = "1"

        for i, (idx, row) in enumerate(df.iterrows()):
            if pd.notna(row["pool"]) and str(row["pool"]).strip().lower() == "x":
                continue
            if pd.notna(row["pool"]) and str(row["pool"]).strip().lower() == "t":
                if row["library_id"]:
                    self.spreadsheet.add_error(i + 1, "pool", "Requested library cannot be marked as control", "invalid_value")
                else:
                    continue
            if pd.isna(row["pool"]):
                self.spreadsheet.add_error(i + 1, "pool", "missing 'pool'", "missing_value")

            if pd.isna(row["library_id"]):
                self.spreadsheet.add_error(i + 1, "library_id", "missing 'library_id'", "missing_value")
            elif row["library_id"] not in self.prep_libraries_df["id"].values:
                self.spreadsheet.add_error(i + 1, "library_id", "invalid 'library_id'", "invalid_value")
            else:
                try:
                    _id = int(row["library_id"])
                except ValueError:
                    self.spreadsheet.add_error(i + 1, "library_id", "invalid 'library_id'", "invalid_value")
                if (library := db.get_library(_id)) is None:
                    self.spreadsheet.add_error(i + 1, "library_id", "invalid 'library_id'", "invalid_value")
                elif library.name != row["library_name"]:
                    self.spreadsheet.add_error(i + 1, "library_name", "invalid 'library_name' for 'library_id'", "invalid_value")
                elif library.lab_prep_id != self.lab_prep.id:
                    self.spreadsheet.add_error(i + 1, "library_id", "Library is not part of this lab prep", "invalid_value")

            if pd.isna(row["library_name"]):
                self.spreadsheet.add_error(i + 1, "library_name", "missing 'library_name'", "missing_value")
            elif row["library_name"] not in self.prep_libraries_df["name"].values:
                self.spreadsheet.add_error(i + 1, "library_name", "invalid 'library_name'", "invalid_value")

            if self.prep_libraries_df[self.prep_libraries_df["id"] == row["library_id"]]["name"].isin([row["library_name"]]).all() == 0:
                self.spreadsheet.add_error(i + 1, "library_name", "invalid 'library_name' for 'library_id'", "invalid_value")

            if (not kit_defined.at[idx]) and (not manual_defined.at[idx]):
                if not pd.isna(row["kit_i7"]):
                    if pd.isna(row["index_well"]) and not pd.isna(row["name_i7"]):
                        self.spreadsheet.add_error(i + 1, "index_well", "missing 'sequence_i7' or 'kit_i7' + 'name_i7' or 'kit_i7' + 'index_well'", "missing_value")
                    if pd.isna(row["name_i7"]) and not pd.isna(row["index_well"]):
                        self.spreadsheet.add_error(i + 1, "name_i7", "missing 'sequence_i7' or 'kit_i7' + 'name_i7' or 'kit_i7' + 'index_well'", "missing_value")
                elif not pd.isna(row["index_well"]) or not pd.isna(row["name_i7"]):
                    self.spreadsheet.add_error(i + 1, "kit_i7", "missing 'sequence_i7' or 'kit_i7' + 'name_i7' or 'kit_i7' + 'index_well'", "missing_value")
                elif pd.isna(row["sequence_i7"]):
                    self.spreadsheet.add_error(i + 1, "sequence_i7", "missing 'sequence_i7' or 'kit_i7' + 'name_i7' or 'kit_i7' + 'index_well'", "missing_value")

        validated = validated and (len(self.spreadsheet._errors) == 0)

        self.df = df
        return validated

    def process_request(self) -> Response:
        if not self.validate():
            self._context["active_tab"] = "spreadsheet"
            return self.make_response()
        
        self.df["kit_i7_name"] = None
        self.df["kit_i5_name"] = None
        self.df["kit_i7_id"] = None
        self.df["kit_i5_id"] = None

        if self.df["kit_i7"].notna().any():
            index_kit_mapping_form = IndexKitMappingForm(uuid=self.uuid)
            index_kit_mapping_form.metadata["lab_prep_id"] = self.lab_prep.id
            index_kit_mapping_form.add_table("library_table", self.df)
            index_kit_mapping_form.update_data()
            index_kit_mapping_form.prepare()
            return index_kit_mapping_form.make_response()
        
        barcode_table_data = {
            "library_id": [],
            "library_name": [],
            "pool": [],
            "sequence_i7": [],
            "sequence_i5": [],
            "name_i7": [],
            "name_i5": [],
        }
        for idx, row in self.df.iterrows():
            seq_i7s = row["sequence_i7"].split(";") if pd.notna(row["sequence_i7"]) else []
            seq_i5s = row["sequence_i5"].split(";") if pd.notna(row["sequence_i5"]) else []
            name_i7s = row["name_i7"].split(";") if pd.notna(row["name_i7"]) else []
            name_i5s = row["name_i5"].split(";") if pd.notna(row["name_i5"]) else []

            for i in range(max(len(seq_i7s), len(seq_i5s))):
                barcode_table_data["library_id"].append(row["library_id"])
                barcode_table_data["library_name"].append(row["library_name"])
                barcode_table_data["pool"].append(row["pool"])
                barcode_table_data["sequence_i7"].append(seq_i7s[i] if len(seq_i7s) > i else None)
                barcode_table_data["sequence_i5"].append(seq_i5s[i] if len(seq_i5s) > i else None)
                barcode_table_data["name_i7"].append(name_i7s[i] if len(name_i7s) > i else None)
                barcode_table_data["name_i5"].append(name_i5s[i] if len(name_i5s) > i else None)
        
        barcode_table = pd.DataFrame(barcode_table_data)

        complete_pool_indexing_form = CompleteLibraryPoolingForm(uuid=self.uuid)
        complete_pool_indexing_form.metadata["lab_prep_id"] = self.lab_prep.id
        complete_pool_indexing_form.add_table("library_table", self.df)
        complete_pool_indexing_form.add_table("barcode_table", barcode_table)
        complete_pool_indexing_form.update_data()
        complete_pool_indexing_form.prepare()
        return complete_pool_indexing_form.make_response()