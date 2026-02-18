from flask import Response
import pandas as pd

from opengsync_db import models

from .... import logger

from ..common import CommonBarcodeInputForm
from .LibraryAnnotationWorkflow import LibraryAnnotationWorkflow


class BarcodeInputForm(LibraryAnnotationWorkflow, CommonBarcodeInputForm):
    _template_path = "workflows/library_annotation/sas-barcode-input.html"

    def __init__(self, seq_request: models.SeqRequest, uuid: str, formdata: dict | None = None):
        LibraryAnnotationWorkflow.__init__(self, seq_request=seq_request, step_name=BarcodeInputForm._step_name, formdata=formdata, uuid=uuid)
        CommonBarcodeInputForm.__init__(
            self, uuid=uuid, workflow=LibraryAnnotationWorkflow._workflow_name,
            formdata=formdata,
            pool=None, lab_prep=None, seq_request=seq_request,
            additional_columns=[]
        )

    def process_request(self) -> Response:
        if not self.validate():
            self._context["kits"] = self.kits
            return self.make_response()
        
        barcode_table = self.df
        barcode_table["index_well"] = barcode_table["index_well"].astype(pd.StringDtype())
        barcode_table["name_i7"] = barcode_table["name_i7"].astype(pd.StringDtype())
        barcode_table["name_i5"] = barcode_table["name_i5"].astype(pd.StringDtype())
        self.tables["barcode_table"] = barcode_table
        return self.get_next_step().make_response()