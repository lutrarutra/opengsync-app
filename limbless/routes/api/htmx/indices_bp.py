from io import StringIO

from flask import Blueprint, redirect, url_for, render_template, flash, request
from flask_restful import Api, Resource
from flask_htmx import make_response
import pandas as pd

from .... import db, logger, forms, tools
from ....core import DBSession

indices_bp = Blueprint("indices_bp", __name__, url_prefix="/api/indices/")
api = Api(indices_bp)

class QueryIndexKits(Resource):
    def post(self):
        library_form = forms.LibraryForm()
        query = library_form.index_kit_search.data

        q_index_kits = db.db_handler.query_indexkit(query)

        return make_response(
            render_template(
                "components/search_select_results.html",
                results=q_index_kits
            ), push_url=False
        )

api.add_resource(QueryIndexKits, "query")
