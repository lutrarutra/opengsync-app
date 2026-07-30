from fastapi import Depends, Query
from fastapi.responses import Response

from opengsync_db import SyncSession

from ...core import dependencies, responses
from ...utils import parsing, barcodes
from ...components import inputs
from ..HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route


class QueryBarcodeSequencesAction(HTMXForm):
    template_path = "actions/query-barcode-sequences.html"

    sequence = inputs.string.StringInputField("Sequence")

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency() -> "QueryBarcodeSequencesAction":
            return QueryBarcodeSequencesAction()
        return dependency

    @htmx_route("GET", "/query-barcode-sequences")
    def Render(cls) -> RouteFunc:
        def route(
            form: "QueryBarcodeSequencesAction" = Depends(QueryBarcodeSequencesAction.Init()),
        ) -> Response:
            return form.make_response()
        return route

    @htmx_route("POST", "/query-barcode-sequences")
    def Search(cls) -> RouteFunc:
        def route(
            sequence: str | None = Query(None),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> Response:
            sequence = parsing.make_alpha_numeric(sequence, keep=[], replace_white_spaces_with="")
            if not sequence:
                return responses.htmx_response(template="components/barcode_results.html")

            sequence = sequence.upper()

            fc_df = session.pd.query_barcode_sequences(sequence, limit=30)
            rc_df = session.pd.query_barcode_sequences(barcodes.reverse_complement(sequence), limit=30)

            return responses.htmx_response(template="components/barcode_results.html",fc_df=fc_df, rc_df=rc_df)
        return route