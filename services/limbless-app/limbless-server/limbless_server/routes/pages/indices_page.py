from flask import Blueprint, render_template
from flask_login import login_required

index_kit_page_bp = Blueprint("index_kit_page", __name__)


@index_kit_page_bp.route("/index_kit")
@login_required
def index_kit_page():
    return render_template("index_kit_page.html")