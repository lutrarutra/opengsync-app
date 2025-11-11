from flask import Response

from opengsync_db import models

from .... import logger, db  # noqa F401
from ...MultiStepForm import StepFile
from ..common import CommonTENXATACBarcodeInputForm
from .VisiumAnnotationForm import VisiumAnnotationForm
from .FeatureAnnotationForm import FeatureAnnotationForm
from .CompleteSASForm import CompleteSASForm
from .BarcodeMatchForm import BarcodeMatchForm
from .OpenSTAnnotationForm import OpenSTAnnotationForm
from .ParseCRISPRGuideAnnotationForm import ParseCRISPRGuideAnnotationForm


class TENXATACBarcodeInputForm(CommonTENXATACBarcodeInputForm):
    _template_path = "workflows/library_annotation/sas-barcode-input.html"
    _workflow_name = "library_annotation"
    seq_request: models.SeqRequest

    def __init__(
        self, seq_request: models.SeqRequest, uuid: str, formdata: dict | None = None
    ):
        CommonTENXATACBarcodeInputForm.__init__(
            self, uuid=uuid, workflow=TENXATACBarcodeInputForm._workflow_name,
            formdata=formdata,
            pool=None, lab_prep=None, seq_request=seq_request,
        )

    def fill_previous_form(self, previous_form: StepFile):
        barcode_table = previous_form.tables["tenx_atac_barcode_table"]

        self.spreadsheet.set_data(barcode_table)
    
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        self.metadata["index_col"] = self.index_col
        barcode_table = self.get_barcode_table()
        self.add_table("tenx_atac_barcode_table", barcode_table)
        self.update_data()

        if BarcodeMatchForm.is_applicable(self):
            next_form = BarcodeMatchForm(seq_request=self.seq_request, uuid=self.uuid)
        elif FeatureAnnotationForm.is_applicable(self):
            next_form = FeatureAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif OpenSTAnnotationForm.is_applicable(self):
            next_form = OpenSTAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif VisiumAnnotationForm.is_applicable(self):
            next_form = VisiumAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif ParseCRISPRGuideAnnotationForm.is_applicable(self):
            next_form = ParseCRISPRGuideAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        else:
            next_form = CompleteSASForm(seq_request=self.seq_request, uuid=self.uuid)
        return next_form.make_response()