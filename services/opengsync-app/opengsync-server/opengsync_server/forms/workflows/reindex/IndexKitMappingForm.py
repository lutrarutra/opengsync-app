from flask import Response

from opengsync_db import models

from ..common import CommonIndexKitMappingForm
from .BarcodeMatchForm import BarcodeMatchForm
from .CompleteReindexForm import CompleteReindexForm


class IndexKitMappingForm(CommonIndexKitMappingForm):
    _template_path = "workflows/reindex/index_kit-mapping.html"
    _workflow_name = "reindex"

    def __init__(
        self,
        seq_request: models.SeqRequest | None,
        lab_prep: models.LabPrep | None,
        pool: models.Pool | None,
        formdata: dict | None,
        uuid: str | None = None
    ):
        CommonIndexKitMappingForm.__init__(
            self, uuid=uuid, workflow=IndexKitMappingForm._workflow_name,
            formdata=formdata,
            pool=pool, lab_prep=lab_prep, seq_request=seq_request
        )
        
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        self.barcode_table = self.fill_barcode_table()
        self.update_table("barcode_table", self.barcode_table)
        
        if BarcodeMatchForm.is_applicable(self):
            form = BarcodeMatchForm(
                seq_request=self.seq_request,
                lab_prep=self.lab_prep,
                pool=self.pool,
                uuid=self.uuid,
                formdata=None
            )
        else:
            form = CompleteReindexForm(
                seq_request=self.seq_request,
                lab_prep=self.lab_prep,
                pool=self.pool,
                uuid=self.uuid,
                formdata=None
            )
        return form.make_response()
