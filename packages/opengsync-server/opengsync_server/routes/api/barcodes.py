from flask import Blueprint, Response, jsonify

from opengsync_db import models
from opengsync_db import queries as Q
from opengsync_db.core.blueprints import pd_transforms as T


from ...core import wrappers, exceptions
from ... import db, forms


barcodes_api_bp = Blueprint("barcodes_api", __name__, url_prefix="/api/barcodes/")


@wrappers.api_route(barcodes_api_bp, db=db, methods=["POST"], json_params=["sequence", "limit"])
def query_barcode_sequence(sequence: str, limit: int = 5) -> Response:
    sequence = sequence.upper()
    fc_df = T.query_barcode_sequences(
        db.session.get_pandas(Q.pd.query_barcode_sequences(sequence, limit), limit=None),
        sequence,
        limit,
    )
    rc_sequence = models.Barcode.reverse_complement(sequence)
    rc_df = T.query_barcode_sequences(
        db.session.get_pandas(Q.pd.query_barcode_sequences(rc_sequence, limit), limit=None),
        rc_sequence,
        limit,
    )

    return jsonify({
        "fc_results": fc_df.to_dict(orient="records"),
        "rc_results": rc_df.to_dict(orient="records"),
    })
    
    
