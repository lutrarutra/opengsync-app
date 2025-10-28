from flask import Response

from opengsync_db import models

from .... import logger
from ..common import CommonBarcodeMatchForm
from .VisiumAnnotationForm import VisiumAnnotationForm
from .FeatureAnnotationForm import FeatureAnnotationForm
from .OpenSTAnnotationForm import OpenSTAnnotationForm
from .CompleteSASForm import CompleteSASForm


class BarcodeMatchForm(CommonBarcodeMatchForm):
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

        self.update_table("barcode_table", self.barcode_table)
        if OpenSTAnnotationForm.is_applicable(self):
            next_form = OpenSTAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif VisiumAnnotationForm.is_applicable(self):
            next_form = VisiumAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif FeatureAnnotationForm.is_applicable(self):
            next_form = FeatureAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        else:
            next_form = CompleteSASForm(seq_request=self.seq_request, uuid=self.uuid)
        return next_form.make_response()