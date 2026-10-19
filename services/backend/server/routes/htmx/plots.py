from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...core import dependencies, responses

router = APIRouter(prefix="/plots", tags=["plots"])

_ADMIN = [Depends(dependencies.require_admin)]


class PlotWidthRequest(BaseModel):
    width: float = 1000


@router.get("/weekday_usage", name="plots_api.weekday_usage", dependencies=_ADMIN)
def weekday_usage():
    return responses.htmx_response(template="components/plots/weekday_usage.html")


@router.post("/weekday_usage", dependencies=_ADMIN)
def weekday_usage_data(body: PlotWidthRequest):
    return responses.htmx_response()
