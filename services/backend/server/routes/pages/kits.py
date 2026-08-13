from fastapi import APIRouter, Depends

from opengsync_db import queries as Q

from ...core import dependencies, responses

router = APIRouter(tags=["kits"])


@router.get("/kits")
def kits_page():
    return responses.html_response("kits_page.html", title="Kits")


@router.get("/kits/{kit_id}")
def kit_page(
    kit_id: int,
    session: dependencies.SyncSession = Depends(dependencies.db_session),
):
    kit = session.get_one(Q.kit.select(id=kit_id))
    return responses.html_response("kit_page.html", kit=kit, title=f"Kit {kit.identifier}")


@router.get("/index-kits")
def index_kits_page():
    return responses.html_response("index_kits_page.html")


@router.get("/index-kits/{index_kit_id}", dependencies=[Depends(dependencies.require_user)])
def index_kit_page(
    index_kit_id: int,
    session: dependencies.SyncSession = Depends(dependencies.db_session),
):
    index_kit = session.get_one(Q.index_kit.select(id=index_kit_id))
    return responses.html_response("index_kit_page.html", index_kit=index_kit, title=f"Index Kit {index_kit.identifier}")


@router.get("/feature-kits")
def feature_kits_page():
    return responses.html_response("feature_kits_page.html", title="Feature Kits")


@router.get("/feature-kits/{feature_kit_id}")
def feature_kit_page(
    feature_kit_id: int,
    session: dependencies.SyncSession = Depends(dependencies.db_session),
):
    feature_kit = session.get_one(Q.feature_kit.select(id=feature_kit_id))
    return responses.html_response("feature_kit_page.html", feature_kit=feature_kit, title=f"Feature Kit {feature_kit.identifier}")
