from typing import Optional

import pandas as pd

from flask import Response, url_for, flash
from flask_htmx import make_response

from limbless_db import models
from limbless_db.categories import LibraryType, LibraryStatus

from .... import logger, tools, db  # noqa F401
from ....tools import SpreadSheetColumn
from ...MultiStepForm import MultiStepForm
from ...SpreadsheetInput import SpreadsheetInput


class FlexMuxForm(MultiStepForm):
    _template_path = "workflows/mux_prep/mux_prep-flex_annotation.html"
    _workflow_name = "mux_prep"
    _step_name = "flex_mux"
    
    columns = [
        SpreadSheetColumn("demux_name", "Demultiplexed Name", "text", 300, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x)),
        SpreadSheetColumn("sample_pool", "Sample Pool", "text", 300, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x)),
        SpreadSheetColumn("barcode_id", "Bardcode ID", "text", 200, str, clean_up_fnc=lambda x: str(x).strip().upper() if pd.notna(x) else None),
    ]

    allowed_barcodes = [f"BC{i:03}" for i in range(1, 17)]

    def __init__(self, lab_prep: models.LabPrep, formdata: dict = {}, uuid: Optional[str] = None):
        MultiStepForm.__init__(
            self, uuid=uuid, formdata=formdata, workflow=FlexMuxForm._workflow_name,
            step_name=FlexMuxForm._step_name, step_args={"multiplexing_type": "flex"}
        )
        self.lab_prep = lab_prep
        self._context["lab_prep"] = self.lab_prep

        if (csrf_token := formdata.get("csrf_token")) is None:
            csrf_token = self.csrf_token._value()  # type: ignore

        self.sample_table = db.get_lab_prep_samples_df(lab_prep.id)
        self.sample_table = self.sample_table[
            (self.sample_table["library_type"] == LibraryType.TENX_SC_GEX_FLEX) |
            (self.sample_table["library_type"] == LibraryType.TENX_SC_ABC_FLEX)
        ]

        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=self.columns, csrf_token=csrf_token,
            post_url=url_for("mux_prep_workflow.parse_flex_annotation", lab_prep_id=self.lab_prep.id, uuid=self.uuid),
            formdata=formdata, df=self.__get_template()
        )

    def __get_template(self) -> pd.DataFrame:
        template_data = {
            "demux_name": [],
            "sample_pool": [],
            "barcode_id": [],
        }

        for _, row in self.sample_table[self.sample_table["library_type"] == LibraryType.TENX_SC_GEX_FLEX].iterrows():
            template_data["demux_name"].append(row["sample_name"])
            template_data["sample_pool"].append(row["sample_pool"])
            template_data["barcode_id"].append(row["flex_barcode"])

        return pd.DataFrame(template_data)

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if not self.spreadsheet.validate():
            return False
        
        df = self.spreadsheet.df

        def padded_barcode_id(s: str) -> str:
            number = ''.join(filter(str.isdigit, s))
            return f"BC{number.zfill(3)}"
        
        df["barcode_id"] = df["barcode_id"].apply(lambda s: padded_barcode_id(s) if pd.notna(s) else None)

        duplicate_barcode = df.duplicated(subset=["sample_pool", "barcode_id"], keep=False)
        
        for i, (idx, row) in enumerate(df.iterrows()):
            if pd.isna(row["demux_name"]):
                self.spreadsheet.add_error(idx, "demux_name", "'Demux Name' is missing.", "missing_value")
            elif row["demux_name"] not in self.sample_table["sample_name"].values:
                self.spreadsheet.add_error(idx, "demux_name", f"Unknown sample '{row['demux_name']}'. Must be one of: {', '.join(self.sample_table['sample_name'])}", "invalid_value")
            
            if pd.isna(row["sample_pool"]):
                self.spreadsheet.add_error(idx, "sample_pool", "'Sample Pool' is missing.", "missing_value")

            if pd.isna(row["barcode_id"]):
                self.spreadsheet.add_error(idx, "barcode_id", "'Barcode ID' is missing.", "missing_value")
            elif row["barcode_id"] not in FlexMuxForm.allowed_barcodes:
                self.spreadsheet.add_error(idx, "barcode_id", f"'Barcode ID' must be one of: {', '.join(FlexMuxForm.allowed_barcodes)}", "invalid_value")
            elif duplicate_barcode.at[idx]:
                self.spreadsheet.add_error(idx, "barcode_id", "'Barcode ID' is duplicated in library.", "duplicate_value")

        if len(self.spreadsheet._errors) > 0:
            return False
        
        self.df = df

        return True

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()

        sample_pool_map = self.df.set_index("demux_name")["sample_pool"].to_dict()
        barcode_id_map = self.df.set_index("demux_name")["barcode_id"].to_dict()
        
        self.sample_table["new_sample_pool"] = self.sample_table["sample_name"].apply(lambda x: sample_pool_map[x])
        self.sample_table["flex_barcode"] = self.sample_table["sample_name"].apply(lambda x: barcode_id_map[x])
        self.sample_table["flex_barcode"] = self.sample_table.apply(
            lambda row: row["flex_barcode"] if row["library_type"] == LibraryType.TENX_SC_GEX_FLEX else row["flex_barcode"].replace("BC", "AB"),
            axis=1
        )

        libraries: dict[str, models.Library] = dict()
        old_libraries: list[int] = []
        
        for _, row in self.sample_table.iterrows():
            if (old_library := db.get_library(int(row["library_id"]))) is None:
                logger.error(f"Library {row['library_id']} not found.")
                raise Exception(f"Library {row['library_id']} not found.")
            
            if old_library.id not in old_libraries:
                old_libraries.append(old_library.id)
            
            if (sample := db.get_sample(int(row["sample_id"]))) is None:
                logger.error(f"Sample {row['sample_id']} not found.")
                raise Exception(f"Sample {row['sample_id']} not found.")
            
            lib = f"{row['new_sample_pool']}_{old_library.type.identifier}"
            if lib not in libraries.keys():
                new_library = db.create_library(
                    name=lib,
                    sample_name=row["new_sample_pool"],
                    library_type=old_library.type,
                    status=LibraryStatus.PREPARING,
                    owner_id=old_library.owner_id,
                    seq_request_id=old_library.seq_request_id,
                    lab_prep_id=self.lab_prep.id,
                    genome_ref=old_library.genome_ref,
                    assay_type=self.lab_prep.assay_type
                )
                libraries[lib] = new_library
            else:
                new_library = libraries[lib]

            db.link_sample_library(sample_id=sample.id, library_id=new_library.id, flex_barcode=row["flex_barcode"])
            new_library.features = old_library.features
            new_library = db.update_library(new_library)

        for old_library_id in old_libraries:
            db.delete_library(old_library_id, delete_orphan_samples=False)

        flash("Changes saved!", "success")
        return make_response(redirect=(url_for("lab_preps_page.lab_prep_page", lab_prep_id=self.lab_prep.id)))