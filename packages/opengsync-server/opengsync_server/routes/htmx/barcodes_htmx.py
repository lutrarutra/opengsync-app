from flask import Blueprint, request

from ... import db, forms
from ...core import wrappers
barcodes_htmx = Blueprint("barcodes_htmx", __name__, url_prefix="/htmx/barcodes/")


@wrappers.htmx_route(barcodes_htmx, db=db, methods=["GET", "POST"])
def query_barcode_sequences():
    if request.method == "GET":
        form = forms.QueryBarcodeSequencesForm()
        return form.make_response()
    
    form = forms.QueryBarcodeSequencesForm(formdata=request.form)
    return form.process_request()