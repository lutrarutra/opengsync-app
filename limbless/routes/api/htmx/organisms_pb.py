from io import StringIO

from flask import Blueprint, redirect, url_for, render_template, flash, request
from flask_restful import Api, Resource
from flask_htmx import make_response
from flask_login import login_required, current_user

from .... import db, logger, forms, tools
from ....core import DBSession

organisms_bp = Blueprint("organisms_bp", __name__, url_prefix="/api/organism/")
api = Api(organisms_bp)

class QueryOrganisms(Resource):
    @login_required
    def post(self):
        sample_form = forms.SampleForm()
        query = sample_form.organism_search.data

        if query == "":
            q_organisms = db.common_organisms
        else:
            try:
                query = int(query)
                if res := db.db_handler.get_organism(query):
                    q_organisms = [res]
                else:
                    q_organisms = []
            except ValueError:
                q_organisms = db.db_handler.query_organisms(query)

        return make_response(
            render_template(
                "components/search_select_results.html",
                results=q_organisms, field_name="organism"
            ), push_url=False
        )
    
api.add_resource(QueryOrganisms, "query")
