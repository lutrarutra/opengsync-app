from flask import Blueprint, render_template
from flask_login import login_required

from limbless_db import DBSession
from ... import db

index_kit_page_bp = Blueprint("index_kit_page", __name__)


@login_required
@index_kit_page_bp.route("/index_kit")
def index_kit_page():
    return render_template("index_kit_page.html")