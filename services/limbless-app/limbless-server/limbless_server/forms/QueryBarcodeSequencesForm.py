from typing import Any

from flask import Response
from wtforms import StringField

from limbless_db import models

from .. import db, logger, tools  # noqa: F401
from .HTMXFlaskForm import HTMXFlaskForm


class QueryBarcodeSequencesForm(HTMXFlaskForm):
    _template_path = "forms/query_barcode_sequences.html"

    sequence = StringField("Sequence")

    def __init__(self, formdata: dict[str, Any] | None = None):
        super().__init__(formdata=formdata)

    def process_request(self) -> Response:
        if not (sequence := tools.make_alpha_numeric(self.sequence.data, keep=[], replace_white_spaces_with="")):
            return self.make_response()
        
        sequence = sequence.upper()
        self.sequence.data = sequence
        
        fc_df = db.query_barcode_sequences_df(sequence, limit=30)
        rc_df = db.query_barcode_sequences_df(models.Barcode.reverse_complement(sequence), limit=30)

        return self.make_response(fc_df=fc_df, rc_df=rc_df)