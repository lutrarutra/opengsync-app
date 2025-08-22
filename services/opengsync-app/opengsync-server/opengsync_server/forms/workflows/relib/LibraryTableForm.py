import pandas as pd

from flask import Response, url_for, flash
from flask_htmx import make_response

from opengsync_db import models
from opengsync_db.categories import LibraryType, GenomeRef, AssayType

from .... import logger, db
from ....core import exceptions
from ....tools import utils
from ....tools.spread_sheet_components import IntegerColumn, TextColumn, DropdownColumn
from ...MultiStepForm import MultiStepForm
from ...SpreadsheetInput import SpreadsheetInput


class LibraryTableForm(MultiStepForm):
    _template_path = "workflows/relib/table_form.html"
    _workflow_name = "relib"
    _step_name = "library_table_form"

    columns = [
        IntegerColumn("library_id", "Library ID", 100, required=True, read_only=True),
        TextColumn("sample_name", "Sample Name", 250, required=True, max_length=models.Library.sample_name.type.length, min_length=4, validation_fnc=utils.check_string),
        TextColumn("library_name", "Library Name", 250, required=True, max_length=models.Library.name.type.length, min_length=4, validation_fnc=utils.check_string),
        DropdownColumn("library_type", "Library Type", 300, choices=LibraryType.names(), required=True),
        DropdownColumn("genome", "Genome", 300, choices=GenomeRef.names(), required=True),
        DropdownColumn("assay_type", "Assay Type", 300, choices=AssayType.names(), required=True),
        DropdownColumn("nuclei_isolation", "Nuclei", 100, choices=["Yes", "No"], required=True),
    ]

    def __init__(
        self,
        seq_request: models.SeqRequest | None,
        lab_prep: models.LabPrep | None,
        pool: models.Pool | None,
        formdata: dict | None,
        uuid: str | None
    ):
        MultiStepForm.__init__(
            self, uuid=uuid, workflow=LibraryTableForm._workflow_name,
            formdata=formdata,
            step_name=LibraryTableForm._step_name,
            step_args={}
        )
        self.seq_request = seq_request
        self.lab_prep = lab_prep
        self.pool = pool

        self.url_context = {}
        if seq_request is not None:
            self._context["seq_request"] = seq_request
            self.url_context["seq_request_id"] = seq_request.id
        if lab_prep is not None:
            self._context["lab_prep"] = lab_prep
            self.url_context["lab_prep_id"] = lab_prep.id
        if pool is not None:
            self._context["pool"] = pool
            self.url_context["pool_id"] = pool.id

        self.library_table = self.tables["library_table"]

        self.post_url = url_for(f"{LibraryTableForm._workflow_name}_workflow.parse_library_type_form", uuid=uuid, **self.url_context)

        self.spreadsheet = SpreadsheetInput(
            columns=LibraryTableForm.columns,
            post_url=self.post_url,
            csrf_token=self._csrf_token,
            formdata=formdata,
            df=self.library_table
        )

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if not self.spreadsheet.validate():
            return False
        
        self.df = self.spreadsheet.df

        self.df = self.__map_library_types(self.df)
        self.df = self.__map_genome_ref(self.df)
        self.df = self.__map_assay_type(self.df)
        return True

    def __map_library_types(self, df: pd.DataFrame) -> pd.DataFrame:
        library_type_map = {}
        for id, e in LibraryType.as_tuples():
            library_type_map[e.display_name] = id
        
        df["library_type_id"] = df["library_type"].map(library_type_map)
        return df

    def __map_genome_ref(self, df: pd.DataFrame) -> pd.DataFrame:
        organism_map = {}
        for id, e in GenomeRef.as_tuples():
            organism_map[e.display_name] = id
        
        df["genome_id"] = df["genome"].map(organism_map)
        return df
    
    def __map_assay_type(self, df: pd.DataFrame) -> pd.DataFrame:
        assay_type_map = {}
        for id, e in AssayType.as_tuples():
            assay_type_map[e.display_name] = id
        
        df["assay_type_id"] = df["assay_type"].map(assay_type_map)
        return df

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        for _, row in self.df.iterrows():
            if (library := db.libraries.get(int(row["library_id"]))) is None:
                logger.error(f"Library with ID {row['library_id']} not found.")
                raise exceptions.NotFoundException()

            library.name = row["library_name"]
            library.sample_name = row["sample_name"]
            library.type = LibraryType.get(row["library_type_id"])
            library.genome_ref = GenomeRef.get(row["genome_id"])
            library.nuclei_isolation = bool(row["nuclei_isolation"] == "Yes")
            library.assay_type = AssayType.get(row["assay_type_id"])
            db.libraries.update(library)

        flash("Changed Saved!", "success")
        if self.seq_request is not None:
            return make_response(redirect=url_for("seq_requests_page.seq_request", seq_request_id=self.seq_request.id))
        
        if self.lab_prep is not None:
            return make_response(redirect=url_for("lab_preps_page.lab_prep", lab_prep_id=self.lab_prep.id))
        
        if self.pool is not None:
            return make_response(redirect=url_for("pools_page.pool", pool_id=self.pool.id))

        return make_response(redirect=url_for("dashboard"))
