from typing import Optional

from flask import Response, url_for, flash
from flask_htmx import make_response
from wtforms import SelectField

from opengsync_db.core import exceptions
from opengsync_db.categories import LibraryStatus

from .... import logger, tools, db  # noqa F401
from ...MultiStepForm import MultiStepForm
from ....tools.spread_sheet_components import IntegerColumn, TextColumn


class ReseqLibrariesForm(MultiStepForm):
    _template_path = "workflows/reseq/reseq.html"
    _workflow_name = "reseq"
    _step_name = "reseq_libraries"

    reprep_type = SelectField(
        "Re-Sequencing Type",
        description="Select the type of re-sequencing to perform.",
        choices=[
            ("indexed", "Indexed"),
            ("raw", "Raw"),
        ],
        default="prepared",
    )

    columns = [
        IntegerColumn("library_id", "Library ID", width=150),
        TextColumn("library_name", "Library Name", width=250),
    ]

    def __init__(
        self, uuid: str | None, formdata: dict | None = None
    ):
        MultiStepForm.__init__(
            self, workflow=ReseqLibrariesForm._workflow_name,
            step_name=ReseqLibrariesForm._step_name, uuid=uuid,
            formdata=formdata, step_args={}
        )
        self.library_table = self.tables["library_table"]
        self.post_url = url_for("reseq_workflow.reseq", uuid=self.uuid)
        self.spreadsheet = tools.StaticSpreadSheet(df=self.library_table, columns=ReseqLibrariesForm.columns)

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        for _, row in self.library_table.iterrows():
            if (library := db.get_library(row["library_id"])) is None:
                logger.error(f"{self.uuid}: Library with ID {row['library_id']} not found")
                raise exceptions.ElementDoesNotExist(f"{self.uuid}: Library with ID {row['library_id']} not found")
            db.clone_library(
                library_id=library.id,
                indexed=True if self.reprep_type.data == "indexed" else False,
                seq_request_id=library.seq_request_id,
                status=LibraryStatus.ACCEPTED
            )

        else:
            logger.error(f"{self.uuid}: Invalid re-sequencing type {self.reprep_type.data}")
            raise ValueError(f"{self.uuid}: Invalid re-sequencing type {self.reprep_type.data}")
        
        flash("Libraries Cloned!", "success")
        
        if (seq_request_id := self.metadata.get("seq_request_id")) is not None:
            if (seq_request := db.get_seq_request(seq_request_id)) is None:
                logger.error(f"{self.uuid}: SeqRequest not found")
                raise ValueError(f"{self.uuid}: SeqRequest not found")
            return make_response(redirect=url_for("seq_requests_page.seq_request", seq_request_id=seq_request.id))
            
        if (lab_prep_id := self.metadata.get("lab_prep_id")) is not None:
            if (lab_prep := db.get_lab_prep(lab_prep_id)) is None:
                logger.error(f"{self.uuid}: LabPrep not found")
                raise ValueError(f"{self.uuid}: LabPrep not found")
            return make_response(redirect=url_for("lab_preps_page.lab_prep", lab_prep_id=lab_prep.id))
        
        return make_response(redirect=url_for("dashboard"))