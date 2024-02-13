from flask import Blueprint, render_template, request, abort

from flask_htmx import make_response
from flask_login import login_required

from limbless_db.core.categories import HttpResponse
from .... import db

organisms_htmx = Blueprint("organisms_htmx", __name__, url_prefix="/api/organisms/")


@organisms_htmx.route("query", methods=["POST"])
@login_required
def query():
    field_name = next(iter(request.form.keys()))
    if (word := request.form.get(field_name, default="")) is None:
        return abort(HttpResponse.BAD_REQUEST.value.id)

    if word.strip() == "":
        q_organisms = db.common_organisms
    else:
        try:
            tax_id = int(word)
            if res := db.get_organism(tax_id):
                q_organisms = [res]
            else:
                q_organisms = []
        except ValueError:
            q_organisms = db.query_organisms(word)

    return make_response(
        render_template(
            "components/search_select_results.html",
            results=q_organisms,
            field_name=field_name
        ), push_url=False
    )
