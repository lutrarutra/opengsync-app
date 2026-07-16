from fastapi import APIRouter, Depends

from opengsync_db import models

from ...core import dependencies, responses

router = APIRouter(tags=["kits"])


@router.get("/kits")
def kits_page():
    return responses.html_response("kits_page.html", title="Kits")


@router.get("/kits/{kit_id}")
def kit_page(kit_id: int):
    # NOTE: Kit lookup and breadcrumb resolution handled client-side.
    return responses.html_response(
        "kit_page.html",
        kit_id=kit_id,
        title=f"Kit {kit_id}",
    )


@router.get("/index-kits")
def index_kits_page():
    return responses.html_response("index_kits_page.html")


@router.get("/index-kits/{index_kit_id}")
def index_kit_page(index_kit_id: int):
    # NOTE: Index kit lookup and breadcrumb resolution handled client-side.
    return responses.html_response(
        "index_kit_page.html",
        index_kit_id=index_kit_id,
        title=f"Kit {index_kit_id}",
    )


@router.get("/feature-kits")
def feature_kits_page():
    return responses.html_response("feature_kits_page.html", title="Feature Kits")


@router.get("/feature-kits/{feature_kit_id}")
def feature_kit_page(feature_kit_id: int):
    # NOTE: Feature kit lookup and breadcrumb resolution handled client-side.
    return responses.html_response(
        "feature_kit_page.html",
        feature_kit_id=feature_kit_id,
        title=f"Feature Kit {feature_kit_id}",
    )