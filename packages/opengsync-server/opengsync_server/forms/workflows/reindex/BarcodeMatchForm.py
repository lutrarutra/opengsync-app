from flask import Response

from opengsync_db import models

from ..common import CommonBarcodeMatchForm
from .CompleteReindexForm import CompleteReindexForm


class BarcodeMatchForm(CommonBarcodeMatchForm):
    _template_path = "workflows/reindex/barcode-match.html"
    _workflow_name = "reindex"
        
    def __init__(
        self,
        seq_request: models.SeqRequest | None,
        lab_prep: models.LabPrep | None,
        pool: models.Pool | None,
        uuid: str, formdata: dict | None = None
    ):
        CommonBarcodeMatchForm.__init__(
            self, uuid=uuid, formdata=formdata, workflow=BarcodeMatchForm._workflow_name,
            seq_request=seq_request,
            pool=pool, lab_prep=lab_prep,
        )

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()

        self.tables["barcode_table"] = self.barcode_table
        self.step()
        form = CompleteReindexForm(
            seq_request=self.seq_request,
            lab_prep=self.lab_prep,
            pool=self.pool,
            uuid=self.uuid,
            formdata=None
        )
        return form.make_response()