from flask import Blueprint, render_template, url_for, make_response, request

from ... import db
from ...core import wrappers, exceptions
kits_page_bp = Blueprint("kits_page", __name__)


@wrappers.page_route(kits_page_bp, db=db, cache_timeout_seconds=360)
def kits():
    return render_template("kits_page.html")


@wrappers.page_route(kits_page_bp, db=db, cache_timeout_seconds=360)
def kit(kit_id: int):
    if (kit := db.kits.get(kit_id)) is None:
        raise exceptions.NotFoundException()

    path_list = [
        ("Kits", url_for("kits_page.kits")),
        (f"Kit {kit_id}", ""),
    ]

    return render_template(
        "kit_page.html", path_list=path_list, kit=kit,
    )


@wrappers.page_route(kits_page_bp, db=db, cache_timeout_seconds=360)
def index_kits():
    return render_template("index_kits_page.html")


@wrappers.page_route(kits_page_bp, db=db, cache_timeout_seconds=360)
def index_kit(index_kit_id: int):
    index_kit = db.index_kits.get(index_kit_id)

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


@wrappers.page_route(kits_page_bp, db=db, cache_timeout_seconds=360)
def feature_kits():
    return render_template("feature_kits_page.html")


@wrappers.page_route(kits_page_bp, db=db, cache_timeout_seconds=360)
def feature_kit(feature_kit_id: int):
    feature_kit = db.feature_kits.get(feature_kit_id)

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


@wrappers.page_route(kits_page_bp, db=db)
def export_features(feature_kit_id: int):
    feature_kit = db.feature_kits.get(feature_kit_id)
    if feature_kit is None:
        raise exceptions.NotFoundException()

    features_df = db.pd.get_feature_kit_features(feature_kit_id=feature_kit_id)
    features_df["feature_type"] = features_df["type"].apply(lambda x: x.modality)

    response = make_response(features_df.to_csv(index=False))
    response.headers["Content-Disposition"] = f"attachment; filename={feature_kit.name.replace(' ', '_').lower()}.csv"
    response.headers["Content-Type"] = "text/csv"
    return response