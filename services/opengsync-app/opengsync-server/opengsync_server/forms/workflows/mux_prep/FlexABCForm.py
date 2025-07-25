from typing import Optional

import pandas as pd

from flask import Response, url_for, flash
from flask_htmx import make_response

from opengsync_db import models, exceptions
from opengsync_db.categories import LibraryType, LibraryStatus, MUXType

from .... import logger, tools, db  # noqa F401
from ....tools import utils
from ....tools.spread_sheet_components import TextColumn, InvalidCellValue, DuplicateCellValue, IntegerColumn
from ...MultiStepForm import MultiStepForm
from ...SpreadsheetInput import SpreadsheetInput


class FlexABCForm(MultiStepForm):
    _template_path = "workflows/mux_prep/mux_prep-flex_abc_annotation.html"
    _workflow_name = "mux_prep"
    _step_name = "flex_abc_annotation"
    
    columns = [
        IntegerColumn("library_id", "Library ID", 100, required=True, read_only=True),
        TextColumn("sample_name", "Demultiplexed Name", 300, required=True, read_only=True),
        TextColumn("barcode_id", "Bardcode ID", 200, required=True, max_length=models.links.SampleLibraryLink.MAX_MUX_FIELD_LENGTH, clean_up_fnc=lambda x: str(x).strip().upper()),
    ]

    allowed_barcodes = [f"AB{i:03}" for i in range(1, 17)]
    mux_type = MUXType.TENX_FLEX_PROBE

    @staticmethod
    def is_applicable(current_step: MultiStepForm) -> bool:
        sample_table = current_step.tables["sample_table"]
        return LibraryType.TENX_SC_ABC_FLEX in sample_table["library_type"].values

    def __init__(self, lab_prep: models.LabPrep, formdata: dict = {}, uuid: Optional[str] = None):
        MultiStepForm.__init__(
            self, uuid=uuid, formdata=formdata, workflow=FlexABCForm._workflow_name,
            step_name=FlexABCForm._step_name, step_args={"mux_type_id": FlexABCForm.mux_type.id}
        )
        self.lab_prep = lab_prep
        self._context["lab_prep"] = self.lab_prep

        self.sample_table = self.tables["sample_table"]
        self.gex_table = self.tables["gex_table"]
        self.abc_table = self.sample_table[
            (self.sample_table["mux_type"].isin([MUXType.TENX_FLEX_PROBE])) &
            (self.sample_table["library_type"].isin([LibraryType.TENX_SC_ABC_FLEX]))
        ].copy()
        self.abc_table["new_sample_pool"] = utils.map_columns(self.abc_table, self.gex_table, "sample_name", "new_sample_pool")

        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=self.columns, csrf_token=self._csrf_token,
            post_url=url_for("mux_prep_workflow.parse_flex_abc_annotation", lab_prep_id=self.lab_prep.id, uuid=self.uuid),
            formdata=formdata
        )

    def prepare(self):
        df = self.abc_table
        df["gex_barcode"] = utils.map_columns(df, self.gex_table, "sample_name", "mux_barcode")
        df["barcode_id"] = df["mux"].apply(lambda x: x.get("barcode") if pd.notna(x) and isinstance(x, dict) else None)
        df.loc[df["barcode_id"].isna(), "barcode_id"] = df.loc[df["barcode_id"].isna(), "gex_barcode"].apply(
            lambda x: x.replace("BC", "AB") if pd.notna(x) else None
        )
        df = df.drop(columns=["gex_barcode"])
        self.spreadsheet.set_data(df)

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if not self.spreadsheet.validate():
            return False
        
        df = self.spreadsheet.df
        df["sample_pool"] = self.gex_table.set_index("sample_name").loc[df["sample_name"], "sample_pool"].values

        def padded_barcode_id(s: str) -> str:
            number = ''.join(filter(str.isdigit, s))
            return f"AB{number.zfill(3)}"
        
        df["barcode_id"] = df["barcode_id"].apply(lambda s: padded_barcode_id(s) if pd.notna(s) else None)
        df["new_sample_pool"] = utils.map_columns(df, self.gex_table, "sample_name", "new_sample_pool")
        duplicate_barcode = df.duplicated(subset=["new_sample_pool", "barcode_id"], keep=False)
        
        for i, (idx, row) in enumerate(df.iterrows()):
            if row["sample_name"] not in self.sample_table["sample_name"].values:
                self.spreadsheet.add_error(idx, "sample_name", InvalidCellValue(f"Unknown sample '{row['sample_name']}'. Must be one of: {', '.join(self.sample_table['sample_name'])}"))
            if row["barcode_id"] not in FlexABCForm.allowed_barcodes:
                self.spreadsheet.add_error(idx, "barcode_id", InvalidCellValue(f"'Barcode ID' must be one of: {', '.join(FlexABCForm.allowed_barcodes)}"))
            elif duplicate_barcode.at[idx]:
                self.spreadsheet.add_error(idx, "barcode_id", DuplicateCellValue("'Barcode ID' is duplicated in library."))

        if len(self.spreadsheet._errors) > 0:
            return False
        
        self.df = df

        return True
    
    @classmethod
    def make_sample_pools(cls, sample_table: pd.DataFrame, lab_prep: models.LabPrep) -> None:
        libraries: dict[str, models.Library] = dict()
        old_libraries: dict[int, models.Library] = dict()

        for library_id in sample_table["library_id"].unique():
            if (library := db.get_library(int(library_id))) is None:
                logger.error(f"Library {library_id} not found.")
                raise exceptions.ElementDoesNotExist(f"Library {library_id} not found.")
            
            old_libraries[library.id] = library
            library.sample_links.clear()
            library = db.update_library(library)
            db.flush()
            db.refresh(library)
        
        for _, row in sample_table.iterrows():
            old_library = old_libraries[int(row["library_id"])]
            
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
                    lab_prep_id=lab_prep.id,
                    genome_ref=old_library.genome_ref,
                    assay_type=old_library.assay_type,
                    mux_type=old_library.mux_type,
                    nuclei_isolation=old_library.nuclei_isolation,
                    index_type=old_library.index_type,
                    original_library_id=old_library.original_library_id if old_library.original_library_id is not None else old_library.id
                )
                libraries[lib] = new_library
            else:
                new_library = libraries[lib]

            db.link_sample_library(
                sample_id=sample.id,
                library_id=new_library.id,
                mux={"barcode": row["mux_barcode"]},
            )
            new_library.features = old_library.features
            new_library = db.update_library(new_library)

        db.flush()
        db.refresh(lab_prep)
        for library in lab_prep.libraries:
            db.refresh(library)
            if len(library.sample_links) == 0:
                db.delete_library(library.id)
        
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        self.abc_table["mux_barcode"] = utils.map_columns(self.abc_table, self.df, ["sample_name", "library_id"], "barcode_id")
        sample_table = pd.concat([self.abc_table, self.gex_table], ignore_index=True).reset_index(drop=True)

        FlexABCForm.make_sample_pools(
            sample_table=sample_table,
            lab_prep=self.lab_prep
        )

        self.complete()
        flash("Changes saved!", "success")
        return make_response(redirect=(url_for("lab_preps_page.lab_prep", lab_prep_id=self.lab_prep.id)))