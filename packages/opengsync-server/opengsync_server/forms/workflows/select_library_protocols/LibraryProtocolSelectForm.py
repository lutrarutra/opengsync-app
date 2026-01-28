import pandas as pd

from flask import Response, url_for, flash
from flask_htmx import make_response

from opengsync_db import models

from .... import db, logger
from ....core import runtime
from ....tools.spread_sheet_components import CategoricalDropDown
from ...MultiStepForm import MultiStepForm
from ...SpreadsheetInput import SpreadsheetInput


class LibraryProtocolSelectForm(MultiStepForm):
    _template_path = "workflows/select_library_protocols/select_library_protocol.html"
    _workflow_name = "select_library_protocols"
    _step_name = "library_protocol_select_form"

    def __init__(self, lab_prep: models.LabPrep, uuid: str | None, formdata: dict | None = None, library_table: pd.DataFrame | None = None):
        super().__init__(formdata=formdata, workflow=LibraryProtocolSelectForm._workflow_name, step_name=LibraryProtocolSelectForm._step_name, uuid=uuid, step_args={})
        self.lab_prep = lab_prep
        self._context["lab_prep"] = lab_prep

        self.library_mappings = {lib.id: lib.name for lib in lab_prep.libraries}
        self.protocol_mappings = {protocol.id: protocol.name for protocol in db.protocols.find(limit=None, sort_by="name")[0]}
        logger.debug(self.library_mappings)
        
        columns: list = [
            CategoricalDropDown("library_id", "Library", 300, categories=self.library_mappings, required=True),
            CategoricalDropDown("protocol_id", "Protocol", 1000, categories=self.protocol_mappings, required=False),
        ]

        if library_table is None:
            self.library_table = self.tables["library_table"]
        else:
            self.library_table = library_table
            self.tables["library_table"] = library_table
            self.step()

        self.library_table["library_id"] = self.library_table["library_id"].astype(pd.Int64Dtype())
        self.library_table["protocol_id"] = self.library_table["protocol_id"].astype(pd.Int64Dtype())

        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=columns, csrf_token=self._csrf_token,
            post_url=url_for("select_library_protocols_workflow.submit", uuid=self.uuid, lab_prep_id=lab_prep.id),
            formdata=formdata, df=self.library_table
        )

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if not self.spreadsheet.validate():
            return False
        
        self.df = self.spreadsheet.df

        if len(self.spreadsheet._errors) > 0:
            return False

        return True

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()

        for _, row in self.df.iterrows():
            if pd.isna(row["library_id"]):
                continue
            library = db.libraries[int(row["library_id"])]
            library.protocol_id = int(row["protocol_id"]) if pd.notna(row["protocol_id"]) else None
            db.libraries.update(library)

        self.complete()
        flash("Protocols Submitted!", "success")
        return make_response(redirect=(url_for("lab_preps_page.lab_prep", lab_prep_id=self.lab_prep.id, tab="lab_prep-checklist-tab")))
        
