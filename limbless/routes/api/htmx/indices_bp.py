from flask import Blueprint, render_template
from flask_restful import Api, Resource
from flask_htmx import make_response
from flask_login import login_required

from .... import db, logger, forms
from ....core import DBSession

indices_bp = Blueprint("indices_bp", __name__, url_prefix="/api/indices/")
api = Api(indices_bp)


class QueryIndexKits(Resource):
    @login_required
    def post(self):
        library_form = forms.LibraryForm()
        query = library_form.index_kit_search.data

        results = db.db_handler.query_indexkit(query)

        return make_response(
            render_template(
                "components/search_select_results.html",
                results=results
            ), push_url=False
        )


class QuerySeqAdapters(Resource):
    @login_required
    def post(self, index_kit_id: int):
        index_form = forms.SCRNAIndexForm()

        query = index_form.adapter_search.data

        results = db.db_handler.query_adapters(
            query, index_kit_id=index_kit_id
        )

        logger.debug(results)

        return make_response(
            render_template(
                "components/search_select_results.html",
                results=results,
                field_name="adapter"
            ), push_url=False
        )


class SelectIndices(Resource):
    @login_required
    def post(self, library_id: int):
        library = db.db_handler.get_library(library_id)
        index_form = forms.DualIndexForm()

        selected_adapter = index_form.adapter.data
        selected_sample_id = index_form.sample.data
        
        with DBSession(db.db_handler) as session:
            indices = session.get_seqindices_by_adapter(selected_adapter)
            selected_sample = session.get_sample(selected_sample_id)

        index_form.index_i7_id.data = indices[0].id
        index_form.index_i5_id.data = indices[1].id
        index_form.index_i7.data = indices[0].sequence
        index_form.index_i5.data = indices[1].sequence

        return make_response(
            render_template(
                "forms/index_forms/dual_index_form.html",
                library=library,
                index_form=index_form,
                available_samples=[sample.to_search_result() for sample in db.db_handler.get_user_samples(2)],
                adapters=db.db_handler.get_adapters_from_kit(library.index_kit_id),
                selected_adapter=selected_adapter,
                selected_sample=selected_sample
            )
        )


api.add_resource(QueryIndexKits, "index_kits/query")
api.add_resource(QuerySeqAdapters, "seq_adapters/query/<int:index_kit_id>")
api.add_resource(SelectIndices, "select_indices/<int:library_id>")
