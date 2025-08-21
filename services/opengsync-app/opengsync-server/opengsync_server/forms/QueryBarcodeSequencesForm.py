from typing import Any

from flask_htmx import make_response
from flask import Response, render_template
from wtforms import StringField

from opengsync_db import models

from .. import db, logger, tools  # noqa: F401
from .HTMXFlaskForm import HTMXFlaskForm


class QueryBarcodeSequencesForm(HTMXFlaskForm):
    _template_path = "forms/query_barcode_sequences.html"

    sequence = StringField("Sequence")

    def __init__(self, formdata: dict[str, Any] | None = None):
        super().__init__(formdata=formdata)

    def process_request(self) -> Response:
        if not (sequence := tools.make_alpha_numeric(self.sequence.data, keep=[], replace_white_spaces_with="")):
            return make_response(render_template("components/barcode_results.html"))
        
        sequence = sequence.upper()
        
        fc_df = db.pd.query_barcode_sequences(sequence, limit=30)
        rc_df = db.pd.query_barcode_sequences(models.Barcode.reverse_complement(sequence), limit=30)

        return make_response(render_template("components/barcode_results.html", fc_df=fc_df, rc_df=rc_df))