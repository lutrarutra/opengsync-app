from flask import Blueprint, render_template, url_for, abort, make_response
from flask_login import login_required

from limbless_db import DBSession
from limbless_db.categories import HTTPResponse

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

    return render_template(
        "feature_kit_page.html",
        path_list=path_list,
        feature_kit=feature_kit,
    )


@feature_kits_page_bp.route("/<int:feature_kit_id>/export_features", methods=["GET"])
@login_required
def export_features(feature_kit_id: int):
    feature_kit = db.get_feature_kit(feature_kit_id)
    if feature_kit is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    features_df = db.get_feature_kit_features_df(feature_kit_id=feature_kit_id)
    features_df["feature_type"] = features_df["type"].apply(lambda x: x.modality)

    response = make_response(features_df.to_csv(index=False))
    response.headers["Content-Disposition"] = f"attachment; filename={feature_kit.name.replace(' ', '_').lower()}.csv"
    response.headers["Content-Type"] = "text/csv"
    return response