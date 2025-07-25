from flask import Blueprint, render_template, url_for, abort, make_response, request
from flask_login import login_required

from opengsync_db import db_session
from opengsync_db.categories import HTTPResponse

from ... import db, page_route

kits_page_bp = Blueprint("kits_page", __name__)


@page_route(kits_page_bp, db=db)
def kits():
    return render_template("kits_page.html")


@page_route(kits_page_bp, db=db)
def kit(kit_id: int):
    if (kit := db.get_kit(kit_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    path_list = [
        ("Kits", url_for("kits_page.kits")),
        (f"Kit {kit_id}", ""),
    ]

    return render_template(
        "kit_page.html", path_list=path_list, kit=kit,
    )


@page_route(kits_page_bp, db=db)
def index_kits():
    return render_template("index_kits_page.html")


@page_route(kits_page_bp, db=db)
def index_kit(index_kit_id: int):
    index_kit = db.get_index_kit(index_kit_id)

    path_list = [
        ("Index Kits", url_for("kits_page.index_kits")),
        (f"Kit {index_kit_id}", ""),
    ]

    if (_from := request.args.get("from", None)) is not None:
        page, id = _from.split("@")
        if page == "library":
            path_list = [
                ("Libraries", url_for("libraries_page.libraries")),
                (f"Library {id}", url_for("libraries_page.library", library_id=id)),
                (f"Kit {index_kit_id}", ""),
            ]

    return render_template(
        "index_kit_page.html", path_list=path_list, index_kit=index_kit,
    )


@page_route(kits_page_bp, db=db)
def feature_kits():
    return render_template("feature_kits_page.html")


@page_route(kits_page_bp, db=db)
def feature_kit(feature_kit_id: int):
    feature_kit = db.get_feature_kit(feature_kit_id)

    path_list = [
        ("Feature Kits", url_for("kits_page.feature_kits")),
        (f"Kit {feature_kit_id}", ""),
    ]

    if (_from := request.args.get("from", None)) is not None:
        page, id = _from.split("@")
        if page == "library":
            path_list = [
                ("Libraries", url_for("libraries_page.libraries")),
                (f"Library {id}", url_for("libraries_page.library", library_id=id)),
                (f"Kit {feature_kit_id}", ""),
            ]

    return render_template(
        "feature_kit_page.html",
        path_list=path_list,
        feature_kit=feature_kit,
    )


@page_route(kits_page_bp, db=db)
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