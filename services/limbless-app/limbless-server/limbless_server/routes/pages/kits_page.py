from flask import Blueprint, render_template, url_for, abort, make_response
from flask_login import login_required

from limbless_db import db_session
from limbless_db.categories import HTTPResponse

from ... import db

kits_page_bp = Blueprint("kits_page", __name__)


@kits_page_bp.route("/kits")
@login_required
def kits_page():
    return render_template("kits_page.html")


@kits_page_bp.route("/kit/<int:kit_id>")
@login_required
def kit_page(kit_id: int):
    kit = db.get_kit(kit_id)

    path_list = [
        ("Kits", url_for("kits_page.kits_page")),
        (f"Kit {kit_id}", ""),
    ]

    return render_template(
        "kit_page.html", path_list=path_list, kit=kit,
    )


@kits_page_bp.route("/index_kits")
@login_required
def index_kits_page():
    return render_template("index_kits_page.html")


@kits_page_bp.route("/index_kits/<int:index_kit_id>")
@login_required
def index_kit_page(index_kit_id: int):
    index_kit = db.get_index_kit(index_kit_id)

    path_list = [
        ("Index Kits", url_for("kits_page.index_kits_page")),
        (f"Kit {index_kit_id}", ""),
    ]

    return render_template(
        "index_kit_page.html", path_list=path_list, index_kit=index_kit,
    )


@kits_page_bp.route("/feature_kits")
@login_required
def feature_kits_page():
    return render_template("feature_kits_page.html")


@kits_page_bp.route("/feature_kits/<int:feature_kit_id>")
@db_session(db)
@login_required
def feature_kit_page(feature_kit_id: int):
    feature_kit = db.get_feature_kit(feature_kit_id)

    path_list = [
        ("Feature Kits", url_for("kits_page.feature_kits_page")),
        (f"Kit {feature_kit_id}", ""),
    ]

    return render_template(
        "feature_kit_page.html",
        path_list=path_list,
        feature_kit=feature_kit,
    )


@kits_page_bp.route("/<int:feature_kit_id>/export_features", methods=["GET"])
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