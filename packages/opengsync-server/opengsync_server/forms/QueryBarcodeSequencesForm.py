from typing import Any

from flask_htmx import make_response
from flask import Response, render_template
from wtforms import StringField

from opengsync_db import models
from opengsync_db import queries as Q
from opengsync_db.core.blueprints import pd_transforms as T

from .. import db, logger, tools
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
        
        fc_df = T.query_barcode_sequences(
            db.session.get_pandas(
                Q.pd.query_barcode_sequences(sequence, 30), limit=None
            ),
            sequence,
            30,
        )
        rc_sequence = models.Barcode.reverse_complement(sequence)
        rc_df = T.query_barcode_sequences(
            db.session.get_pandas(
                Q.pd.query_barcode_sequences(rc_sequence, 30), limit=None
            ),
            rc_sequence,
            30,
        )

        return make_response(render_template("components/barcode_results.html", fc_df=fc_df, rc_df=rc_df))