from flask import Blueprint, render_template, url_for
from flask_login import login_required

from limbless_db import DBSession
from ... import db

feature_kits_page_bp = Blueprint("feature_kits_page", __name__)


@feature_kits_page_bp.route("/feature_kits")
@login_required
def feature_kits_page():
    return render_template("feature_kits_page.html")


@feature_kits_page_bp.route("/feature_kits/<int:feature_kit_id>")
@login_required
def feature_kit_page(feature_kit_id: int):
    with DBSession(db) as session:
        feature_kit = session.get_feature_kit(feature_kit_id)

    path_list = [
        ("Feature Kits", url_for("feature_kits_page.feature_kits_page")),
        (f"{feature_kit_id}", ""),
    ]

    features, features_n_pages = session.get_features(feature_kit_id=feature_kit_id, sort_by="id", descending=True)

    return render_template(
        "feature_kit_page.html",
        path_list=path_list,
        feature_kit=feature_kit,
        features=features,
        features_n_pages=features_n_pages,
        features_active_page=0,
        features_current_sort="id",
        features_current_sort_order="desc",
    )