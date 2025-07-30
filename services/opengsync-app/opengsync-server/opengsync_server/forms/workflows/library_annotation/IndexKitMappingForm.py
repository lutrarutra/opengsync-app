from flask import Response

import pandas as pd

from opengsync_db import models
from opengsync_db.categories import LibraryType, IndexType

from .... import db, logger
from ..common import CommonIndexKitMappingForm
from .OligoMuxAnnotationForm import OligoMuxAnnotationForm
from .VisiumAnnotationForm import VisiumAnnotationForm
from .FeatureAnnotationForm import FeatureAnnotationForm
from .FlexAnnotationForm import FlexAnnotationForm
from .SampleAttributeAnnotationForm import SampleAttributeAnnotationForm
from .OCMAnnotationForm import OCMAnnotationForm
from .OpenSTAnnotationForm import OpenSTAnnotationForm


class IndexKitMappingForm(CommonIndexKitMappingForm):
    _template_path = "workflows/library_annotation/sas-index_kit-mapping-form.html"
    _workflow_name = "library_annotation"
    seq_request: models.SeqRequest

    def __init__(self, seq_request: models.SeqRequest, uuid: str, formdata: dict | None = None):
        CommonIndexKitMappingForm.__init__(
            self, uuid=uuid, formdata=formdata, workflow=IndexKitMappingForm._workflow_name,
            seq_request=seq_request, pool=None, lab_prep=None,
        )
        
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        self.barcode_table = self.fill_barcode_table()
        self.add_table("index_kit_table", self.kit_table)
        self.update_table("barcode_table", self.barcode_table, update_data=True)

        if OCMAnnotationForm.is_applicable(self):
            next_form = OCMAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif OligoMuxAnnotationForm.is_applicable(self):
            next_form = OligoMuxAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif OpenSTAnnotationForm.is_applicable(self):
            next_form = OpenSTAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif VisiumAnnotationForm.is_applicable(self):
            next_form = VisiumAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif FeatureAnnotationForm.is_applicable(self):
            next_form = FeatureAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif FlexAnnotationForm.is_applicable(self, seq_request=self.seq_request):
            next_form = FlexAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        else:
            next_form = SampleAttributeAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        return next_form.make_response()