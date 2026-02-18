from flask import Response

from opengsync_db import models

from .... import logger
from ..common import CommonBarcodeMatchForm
from .LibraryAnnotationWorkflow import LibraryAnnotationWorkflow


class BarcodeMatchForm(LibraryAnnotationWorkflow, CommonBarcodeMatchForm):
    _template_path = "workflows/library_annotation/sas-barcode-match.html"
    _workflow_name = "library_annotation"
    seq_request: models.SeqRequest
        
    def __init__(self, seq_request: models.SeqRequest, uuid: str, formdata: dict | None = None):
        CommonBarcodeMatchForm.__init__(
            self, uuid=uuid, formdata=formdata, workflow=BarcodeMatchForm._workflow_name,
            seq_request=seq_request,
            pool=None, lab_prep=None,
        )

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        if self.i7_option.data is not None:
            self.add_comment(
                context="i7_option",
                text=f"{dict(self.i7_option.choices)[self.i7_option.data]}: {', '.join(self.barcode_table['library_name'].unique().tolist())}",  # type: ignore
            )

        if self.i5_option.data is not None:
            self.add_comment(
                context="i5_option",
                text=f"{dict(self.i5_option.choices)[self.i5_option.data]}: {', '.join(self.barcode_table['library_name'].unique().tolist())}",  # type: ignore
            )

        self.tables["barcode_table"] = self.barcode_table
        return self.get_next_step().make_response()