from fastapi import APIRouter, Depends

from opengsync_db import models

from ...core import dependencies, responses

router = APIRouter(tags=["kits"])


@router.get("/kits")
async def kits():
    return await responses.html_response("kits_page.html", title="Kits")


@router.get("/kits/{kit_id}")
async def kit(kit_id: int):
    # NOTE: Kit lookup and breadcrumb resolution handled client-side.
    return await responses.html_response(
        "kit_page.html",
        kit_id=kit_id,
        title=f"Kit {kit_id}",
    )


@router.get("/index-kits")
async def index_kits():
    return await responses.html_response("index_kits_page.html")


@router.get("/index-kits/{index_kit_id}")
async def index_kit(index_kit_id: int):
    # NOTE: Index kit lookup and breadcrumb resolution handled client-side.
    return await responses.html_response(
        "index_kit_page.html",
        index_kit_id=index_kit_id,
        title=f"Kit {index_kit_id}",
    )


@router.get("/feature-kits")
async def feature_kits():
    return await responses.html_response("feature_kits_page.html", title="Feature Kits")


@router.get("/feature-kits/{feature_kit_id}")
async def feature_kit(feature_kit_id: int):
    # NOTE: Feature kit lookup and breadcrumb resolution handled client-side.
    return await responses.html_response(
        "feature_kit_page.html",
        feature_kit_id=feature_kit_id,
        title=f"Feature Kit {feature_kit_id}",
    )