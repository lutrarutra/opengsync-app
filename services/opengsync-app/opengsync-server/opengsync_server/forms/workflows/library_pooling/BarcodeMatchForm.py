from flask import Response

from opengsync_db import models

from .... import logger, tools, db  # noqa F401
from ..common import CommonBarcodeMatchForm
from .CompleteLibraryPoolingForm import CompleteLibraryPoolingForm


class BarcodeMatchForm(CommonBarcodeMatchForm):
    _template_path = "workflows/library_pooling/barcode-match.html"
    _workflow_name = "library_pooling"
    lab_prep: models.LabPrep
        
    def __init__(
        self,
        lab_prep: models.LabPrep,
        uuid: str, formdata: dict | None = None
    ):
        CommonBarcodeMatchForm.__init__(
            self, uuid=uuid, formdata=formdata, workflow=BarcodeMatchForm._workflow_name,
            seq_request=None, pool=None, lab_prep=lab_prep,
        )

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()

        self.update_table("barcode_table", self.barcode_table)
        form = CompleteLibraryPoolingForm(
            lab_prep=self.lab_prep,
            uuid=self.uuid,
            formdata=None
        )
        return form.make_response()