from flask import Response
import pandas as pd

from opengsync_db import models

from .... import logger

from ..common import CommonBarcodeInputForm
from .VisiumAnnotationForm import VisiumAnnotationForm
from .FeatureAnnotationForm import FeatureAnnotationForm
from .CompleteSASForm import CompleteSASForm
from .BarcodeMatchForm import BarcodeMatchForm
from .OpenSTAnnotationForm import OpenSTAnnotationForm
from .TENXATACBarcodeInputForm import TENXATACBarcodeInputForm
from .ParseCRISPRGuideAnnotationForm import ParseCRISPRGuideAnnotationForm


class BarcodeInputForm(CommonBarcodeInputForm):
    _template_path = "workflows/library_annotation/sas-barcode-input.html"
    _workflow_name = "library_annotation"
    seq_request: models.SeqRequest

    def __init__(self, seq_request: models.SeqRequest, uuid: str, formdata: dict | None = None):
        CommonBarcodeInputForm.__init__(
            self, uuid=uuid, workflow=BarcodeInputForm._workflow_name,
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
        logger.debug(barcode_table)
        logger.debug(barcode_table.dtypes)
        self.step()

        if BarcodeMatchForm.is_applicable(self):
            next_form = BarcodeMatchForm(seq_request=self.seq_request, uuid=self.uuid)
        elif TENXATACBarcodeInputForm.is_applicable(self):
            next_form = TENXATACBarcodeInputForm(seq_request=self.seq_request, uuid=self.uuid)
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