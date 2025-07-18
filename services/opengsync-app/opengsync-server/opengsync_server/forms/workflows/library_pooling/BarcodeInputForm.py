import os
import re
from typing import Optional

import pandas as pd

from flask import Response, current_app, url_for
from wtforms import SelectField, FormField
from flask_wtf import FlaskForm

from opengsync_db import models

from .... import logger, tools, db  # noqa F401
from ....tools.spread_sheet_components import IntegerColumn, TextColumn, DropdownColumn, InvalidCellValue, MissingCellValue
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
        IntegerColumn("library_id", "ID", 50, required=True),
        DropdownColumn("library_name", "Library Name", 250, required=True, choices=[]),
        TextColumn("index_well", "Well", 70, max_length=8, clean_up_fnc=lambda x: index_well_clean_up_fnc(x)),
        TextColumn("pool", "Pool", 70, required=True, max_length=models.Pool.name.type.length),
        TextColumn("kit_i7", "i7 Kit", 200, max_length=models.Kit.name.type.length),
        TextColumn("name_i7", "i7 Name", 150, max_length=models.LibraryIndex.name_i7.type.length),
        TextColumn("sequence_i7", "i7 Sequence", 180),
        TextColumn("kit_i5", "i5 Kit", 200, max_length=models.Kit.name.type.length),
        TextColumn("name_i5", "i5 Name", 150, max_length=models.LibraryIndex.name_i5.type.length),
        TextColumn("sequence_i5", "i5 Sequence", 180),
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
        self.spreadsheet.columns["library_name"].source = self.prep_libraries_df["name"].tolist()

    def get_template(self) -> pd.DataFrame:
        if self.lab_prep.prep_file is not None:
            prep_table = pd.read_excel(os.path.join(current_app.config["MEDIA_FOLDER"], self.lab_prep.prep_file.path), "prep_table")  # type: ignore
            prep_table = prep_table.dropna(subset=["library_id", "library_name"])
            df = prep_table[[col.label for col in BarcodeInputForm.columns]].copy()
        else:
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

            df = pd.DataFrame(library_data).sort_values("library_id", ascending=True)

        df.loc[df["kit_i7"].notna(), ["sequence_i7"]] = None
        df.loc[df["kit_i5"].notna(), ["sequence_i5"]] = None
        df.loc[df["name_i7"].notna(), "name_i7"] = df.loc[df["name_i7"].notna(), "name_i7"].apply(lambda x: ";".join(list(set(x.split(";")))))
        df.loc[df["name_i5"].notna(), "name_i5"] = df.loc[df["name_i5"].notna(), "name_i5"].apply(lambda x: ";".join(list(set(x.split(";")))))

        return df
    
    def fill_previous_form(self, previous_form: MultiStepForm):
        self.spreadsheet.set_data(previous_form.tables["library_table"])
    
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
        seq_i7_max_length = df["sequence_i7"].apply(lambda x: max(((len(s) for s in x.split(";") if pd.notna(s)) if pd.notna(x) else ""), default=0))
        seq_i5_max_length = df["sequence_i5"].apply(lambda x: max(((len(s) for s in x.split(";") if pd.notna(s)) if pd.notna(x) else ""), default=0))

        df.loc[df["kit_i5"].isna(), "kit_i5"] = df.loc[df["kit_i5"].isna(), "kit_i7"]
        df.loc[df["name_i5"].isna(), "name_i5"] = df.loc[df["name_i5"].isna(), "name_i7"]

        if df.loc[~df["pool"].astype(str).str.strip().str.lower().isin(["x", "t"]), "pool"].isna().all():
            df.loc[df["pool"].isna(), "pool"] = "1"

        for i, (idx, row) in enumerate(df.iterrows()):
            if pd.notna(row["pool"]) and str(row["pool"]).strip().lower() == "x":
                continue
            if pd.notna(row["pool"]) and str(row["pool"]).strip().lower() == "t":
                if row["library_id"]:
                    self.spreadsheet.add_error(idx, "pool", InvalidCellValue("Requested library cannot be marked as control"))
                else:
                    continue

            if row["library_id"] not in self.prep_libraries_df["id"].values:
                self.spreadsheet.add_error(idx, "library_id", InvalidCellValue("invalid 'library_id'"))
            else:
                try:
                    _id = int(row["library_id"])
                except ValueError:
                    self.spreadsheet.add_error(idx, "library_id", InvalidCellValue("invalid 'library_id'"))
                if (library := db.get_library(_id)) is None:
                    self.spreadsheet.add_error(idx, "library_id", InvalidCellValue("invalid 'library_id'"))
                elif library.name != row["library_name"]:
                    self.spreadsheet.add_error(idx, "library_name", InvalidCellValue("invalid 'library_name' for 'library_id'"))
                elif library.lab_prep_id != self.lab_prep.id:
                    self.spreadsheet.add_error(idx, "library_id", InvalidCellValue("Library is not part of this lab prep"))

            if row["library_name"] not in self.prep_libraries_df["name"].values:
                self.spreadsheet.add_error(idx, "library_name", InvalidCellValue("invalid 'library_name'"))

            if self.prep_libraries_df[self.prep_libraries_df["id"] == row["library_id"]]["name"].isin([row["library_name"]]).all() == 0:
                self.spreadsheet.add_error(idx, "library_name", InvalidCellValue("invalid 'library_name' for 'library_id'"))

            if (not kit_defined.at[idx]) and (not manual_defined.at[idx]):
                logger.debug(row)
                if pd.notna(row["kit_i7"]):
                    if pd.isna(row["index_well"]) and pd.isna(row["name_i7"]):
                        self.spreadsheet.add_error(idx, ["index_well", "name_i7"], MissingCellValue("'index_well' or 'name_i7' must be defined when kit is defined"))
                elif pd.notna(row["index_well"]) or pd.notna(row["name_i7"]):
                    self.spreadsheet.add_error(idx, "kit_i7", MissingCellValue("missing 'sequence_i7' or 'kit_i7' + 'name_i7' or 'kit_i7' + 'index_well'"))
                elif pd.isna(row["sequence_i7"]):
                    self.spreadsheet.add_error(idx, "sequence_i7", MissingCellValue("missing 'sequence_i7' or 'kit_i7' + 'name_i7' or 'kit_i7' + 'index_well'"))

            if seq_i7_max_length.at[idx] > models.LibraryIndex.sequence_i7.type.length:
                self.spreadsheet.add_error(idx, "sequence_i7", InvalidCellValue(f"i7 sequence too long ({seq_i7_max_length.at[idx]} > {models.LibraryIndex.sequence_i7.type.length})"))
            
            if seq_i5_max_length.at[idx] > models.LibraryIndex.sequence_i5.type.length:
                self.spreadsheet.add_error(idx, "sequence_i5", InvalidCellValue(f"i5 sequence too long ({seq_i5_max_length.at[idx]} > {models.LibraryIndex.sequence_i5.type.length})"))

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

        self.metadata["lab_prep_id"] = self.lab_prep.id
        self.add_table("barcode_table", barcode_table)
        self.add_table("library_table", self.df)
        self.update_data()

        if IndexKitMappingForm.is_applicable(self):
            form = IndexKitMappingForm(lab_prep=self.lab_prep, uuid=self.uuid)
            form.prepare()
            return form.make_response()

        form = CompleteLibraryPoolingForm(lab_prep=self.lab_prep, uuid=self.uuid)
        form.prepare()
        return form.make_response()