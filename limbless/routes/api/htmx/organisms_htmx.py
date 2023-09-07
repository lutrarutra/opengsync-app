from flask import Blueprint, render_template, request

from flask_htmx import make_response
from flask_login import login_required

from .... import db, logger

organisms_htmx = Blueprint("organisms_htmx", __name__, url_prefix="/api/organism/")


@login_required
@organisms_htmx.route("query", methods=["GET"])
def query():
    field_name = next(iter(request.args.keys()))
    query = request.args.get(field_name)
    assert query is not None

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
            results=q_organisms,
            field_name=field_name
        ), push_url=False
    )
