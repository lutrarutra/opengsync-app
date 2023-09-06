from flask import Blueprint, render_template

from flask_htmx import make_response
from flask_login import login_required

from .... import db, logger, forms

organisms_htmx = Blueprint("organisms_htmx", __name__, url_prefix="/api/organism/")


@login_required
@organisms_htmx.route("query", methods=["POST"])
def query():
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
